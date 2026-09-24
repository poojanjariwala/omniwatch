"""CCTV ingestion orchestrator.

ingest_once(db, camera): pull samples from the resolved detector for one
ingest cycle, persist a CctvEvent, update the adaptive baseline, and raise an
explainable alert when the anomaly rules fire.

The same function runs (a) synchronously inside the API in broker-less demo
mode and (b) inside a Celery worker in the composed deployment, so heavy AI
work never blocks core operations.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from sqlalchemy.orm import Session

from app.models.common import SEVERITY_CRITICAL, SEVERITY_WARNING, utcnow
from app.models.cv import Baseline, Camera, CctvEvent
from app.models.ops import Alert, Distribution, Project, QrCode
from app.services import alerts as alert_svc
from app.services.cv.anomaly import evaluate_window, updated_baseline
from app.services.cv.detectors import resolve_detector


def _get_baseline(db: Session, project_id: int) -> Baseline:
    base = db.query(Baseline).filter(Baseline.project_id == project_id).first()
    if base is None:
        base = Baseline(project_id=project_id, ewma=0.0, ewma_items=0.0,
                        sample_count=0, updated_at=utcnow())
        db.add(base)
        db.flush()
    return base


def ingest_once(db: Session, camera: Camera, *, profile: list[dict] | None = None,
                actor_id: int | None = None) -> dict:
    """Process one ingest cycle for a camera. Returns a summary dict."""
    if not camera.enabled:
        return {"camera": camera.id, "skipped": "disabled"}

    detector = resolve_detector(camera, force_sim=bool(profile))
    samples = list(detector.samples(
        source=camera.url or "",
        seconds=max(1, camera.ingest_every_seconds),
        profile=profile,
    ))
    if not samples:
        return {"camera": camera.id, "frames": 0, "skipped": "no_samples"}

    occupancy = max(s.occupancy for s in samples)
    items = sum(s.items_handed or 0 for s in samples)
    window_seconds = max(1, len(samples))

    event = CctvEvent(
        camera_id=camera.id,
        project_id=camera.project_id,
        ts=samples[-1].ts,
        occupancy=occupancy,
        items_handed=items,
        window_seconds=window_seconds,
        processed_by=detector.backend_name,
        samples=[{"ts": s.ts.isoformat(), "occ": s.occupancy} for s in samples[:12]],
    )
    db.add(event)
    db.flush()

    baseline = _get_baseline(db, camera.project_id)
    verdict = evaluate_window(
        occupancy=occupancy, items=items,
        ewma=baseline.ewma, ewma_items=baseline.ewma_items,
        sample_count=baseline.sample_count, window_seconds=window_seconds,
    )

    project = db.get(Project, camera.project_id)
    alert_payload = None
    if verdict.flagged:
        cooled = alert_svc.open_alert_exists(db, project_id=project.id,
                                             kind=verdict.kind or "activity_surge",
                                             minutes=15)
        if not cooled:
            signals = list(verdict.signals)
            signals.append({"type": "camera", "name": camera.name,
                            "source_type": camera.source_type,
                            "detector": detector.backend_name,
                            "window_ts": samples[-1].ts.isoformat()})
            signals.append({"type": "what_where_when",
                            "what": verdict.explanation,
                            "where": f"{project.name} ({project.code})",
                            "when": samples[-1].ts.isoformat()})
            recommendation = (
                f"Verify with a blind surprise inspection during the flagged window; "
                f"cross-check CCTV occupancy against reported attendance and QR "
                f"consumption before any decision. "
            )
            alert = alert_svc.create_alert(
                db,
                kind=verdict.kind or "activity_surge",
                severity=verdict.severity,
                title="Sudden activity surge detected" if verdict.kind == "activity_surge"
                else "Tip-off / staged activity suspected",
                summary=verdict.explanation,
                project=project,
                signals=signals,
                risk_signal=verdict.risk,
                recommended_action=recommendation,
                ai_generated=True,
                actor_id=actor_id,
            )
            alert_payload = {"code": alert.code, "severity": alert.severity,
                             "risk": alert.risk_signal}
            alert_svc.update_project_risk(db, project)

    # Update baseline only for non-alerting windows (outliers can't poison EWMA).
    if not verdict.flagged:
        ewma, ewma_i, count = updated_baseline(
            baseline.ewma, baseline.ewma_items, baseline.sample_count,
            occupancy, items,
        )
        baseline.ewma, baseline.ewma_items, baseline.sample_count = ewma, ewma_i, count
        baseline.updated_at = utcnow()

    camera.last_ingest_at = utcnow()
    camera.last_frame_count = occupancy
    db.commit()

    return {
        "camera": camera.id,
        "frames": len(samples),
        "occupancy": occupancy,
        "items": items,
        "processed_by": detector.backend_name,
        "window_seconds": window_seconds,
        "baseline_ewma": baseline.ewma,
        "flagged": verdict.flagged,
        "alert": alert_payload,
        "explanation": verdict.explanation,
    }


def ingest_project_cameras(db: Session, project_id: int | None = None) -> list[dict]:
    q = db.query(Camera).filter(Camera.enabled.is_(True))
    if project_id:
        q = q.filter(Camera.project_id == project_id)
    out = []
    for cam in q.all():
        try:
            out.append(ingest_once(db, cam))
        except Exception as exc:  # noqa: BLE001 - keep one bad stream from stopping others
            cam.last_error = str(exc)[:500]
            db.commit()
            out.append({"camera": cam.id, "error": str(exc)[:200]})
    return out


# ---------------------------------------------------------------------------
# Cross-channel reconciliation (reported vs independently observed)
# ---------------------------------------------------------------------------

def reconcile_project(db: Session, project: Project, actor_id: int | None = None) -> Alert | None:
    """Compare self-reported beneficiary counts against QR + CCTV observations.

    Flags only when the site is demonstrably operating (QR activity or CCTV
    frames today) yet verified handouts fall far short of the self-reported
    figure. Output is advisory; verification remains with officials.
    """
    reported = project.reported_beneficiaries or 0
    if reported <= 0:
        return None
    today = utcnow().date()
    day_start = datetime.combine(today, time.min, tzinfo=timezone.utc)

    consumed = (db.query(QrCode)
                .filter(QrCode.project_id == project.id,
                        QrCode.status == "consumed",
                        QrCode.consumed_at >= day_start).count())
    open_dists = db.query(Distribution).filter(Distribution.project_id == project.id).count()

    cctv_avg = None
    events = (db.query(CctvEvent)
              .filter(CctvEvent.project_id == project.id,
                      CctvEvent.ts >= day_start).all())
    if events:
        cctv_avg = round(sum(e.occupancy for e in events) / len(events), 1)

    site_operating = (consumed > 0) or bool(events)
    verified_share = consumed / reported if reported else 0.0
    low_handouts = consumed < 0.3 * reported
    if not (site_operating and low_handouts and open_dists > 0):
        return None
    if alert_svc.open_alert_exists(db, project_id=project.id, kind="reconciliation",
                                   minutes=24 * 60):
        return None

    signals = [
        {"type": "reported", "beneficiaries": reported, "source": "self-report"},
        {"type": "qr_consumed_today", "count": consumed, "source": "independent"},
        {"type": "cctv_avg_occupancy_today", "count": cctv_avg, "source": "independent"},
        {"type": "verified_share", "value": round(verified_share, 3)},
    ]
    cctv_line = f" CCTV typical occupancy {cctv_avg}." if cctv_avg is not None else ""
    risk = min(1.0, 0.5 + (1.0 - verified_share) * 0.5)
    alert = alert_svc.create_alert(
        db,
        kind="reconciliation",
        severity=SEVERITY_CRITICAL if risk >= 0.7 else SEVERITY_WARNING,
        title="Reported beneficiaries exceed verified handouts",
        summary=(f"{project.name} self-reports {reported} beneficiaries, but only "
                 f"{consumed} QR-verified handouts were recorded today "
                 f"({int(verified_share * 100)}% of claimed).{cctv_line}"),
        project=project,
        signals=signals,
        risk_signal=risk,
        recommended_action=("Field-verify the register with a random inspection; "
                            "do not treat the discrepancy as fraud without human verification."),
        ai_generated=True,
        actor_id=actor_id,
    )
    db.flush()
    alert_svc.update_project_risk(db, project)
    db.commit()
    return alert
