"""Demo scenario runners — available ONLY when DEMO_MODE=true.

Each call drives the same services the production flows use (no special
backend), producing auditable state the UI and the test suite can replay.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings
from app.core.limits import limiter
from app.core.rbac import Db, DosjeUser
from app.models.cv import Camera
from app.models.ops import Alert, OutdoorEvent, Project, QrCode
from app.models.users import Organization, User  # noqa: F401  (typed helper use)
from app.services import alerts as alert_svc
from app.services import events as event_svc
from app.services.cv.engine import ingest_once
from app.services.dispatch import pick_and_assign
from app.services.qr import scan_code

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _guard():
    if not settings.demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")


def _project_by_code(db, code: str) -> Project:
    project = db.query(Project).filter(Project.code == code).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Project {code} not found")
    return project


@router.post("/scenario/a")
@limiter.limit("5/minute")
def scenario_a(request: Request, db: Db, user: DosjeUser,
               project_code: str = "DEMO-CENTRE-01"):
    """A — sudden surge: scripted CCTV spike → explainable alert → blind dispatch."""
    _guard()
    project = _project_by_code(db, project_code)
    camera = db.query(Camera).filter(Camera.project_id == project.id,
                                     Camera.enabled.is_(True)).first()
    if camera is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="No enabled camera for the project")

    normal = [{"occupancy": 8, "items": 6}, {"occupancy": 9, "items": 7},
              {"occupancy": 10, "items": 8}, {"occupancy": 9, "items": 7},
              {"occupancy": 11, "items": 8}, {"occupancy": 10, "items": 7}]
    surge = [{"occupancy": 12 + i, "items": 8} for i in range(1, 30)]  # ramp to ~41
    result = ingest_once(db, camera, profile=normal + surge, actor_id=user.id)

    alert_out = None
    inspection_out = None
    if result.get("alert"):
        alert = db.query(Alert).filter(Alert.code == result["alert"]["code"]).first()
        alert_out = {"code": alert.code, "severity": alert.severity,
                     "risk": alert.risk_signal, "status": alert.status}
        if alert.project_id:
            try:
                insp, event, dispatch_rec = pick_and_assign(
                    db, project=project, actor=user, kind="random_surge",
                    risk_signal=alert.risk_signal, trigger_alert_id=alert.id,
                    reason=f"Verify surge alert {alert.code}",
                )
                alert.inspection_id = insp.id
                db.flush()
                alert_svc.transition_alert(db, alert, "verifying", actor_id=user.id,
                                           note="Blind inspection dispatched")
                inspection_out = {
                    "id": insp.id, "code": insp.code, "status": insp.status,
                    "inspector_id": insp.assigned_inspector_id,
                    "rationale": dispatch_rec.rationale,
                }
                db.commit()
            except ValueError as exc:  # noqa: BLE001
                inspection_out = {"error": str(exc)}
                db.commit()
    return {
        "camera_id": camera.id,
        "ingest": {k: v for k, v in result.items() if k not in ("frames", "camera")},
        "alert": alert_out,
        "inspection": inspection_out,
        "next": ["Open the alert, then log in as the assigned inspector to activate the task."],
    }


@router.post("/scenario/b")
@limiter.limit("5/minute")
def scenario_b(request: Request, db: Db, user: DosjeUser,
               project_code: str = "DEMO-DIST-01"):
    """B — item recycling: consume a QR once, then replay the same code."""
    _guard()
    project = _project_by_code(db, project_code)
    code_row = db.query(QrCode).filter(QrCode.project_id == project.id,
                                       QrCode.status == "issued") \
        .order_by(QrCode.id).first()
    if code_row is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="No issued QR code available — issue a batch first")
    first = scan_code(db, actor=user, code_str=code_row.code,
                      lat=project.lat, lng=project.lng, recipient_token="DEMO-BEN-001")
    replay = scan_code(db, actor=user, code_str=code_row.code,
                       lat=project.lat, lng=project.lng, recipient_token="DEMO-BEN-001")
    alert = db.query(Alert).filter(Alert.kind == "qr_replay",
                                   Alert.project_id == project.id) \
        .order_by(Alert.occurred_at.desc()).first()
    return {
        "code": code_row.code,
        "first_scan": first,
        "replay_scan": replay,
        "alert_code": alert.code if alert else None,
        "note": "Replay blocked server-side; anomaly alert visible to government roles only.",
    }


@router.post("/scenario/c")
@limiter.limit("5/minute")
def scenario_c(request: Request, db: Db, user: DosjeUser,
               project_code: str = "DEMO-OUTDOOR-01"):
    """C — outdoor event: register 48h+ ahead, approve, broadcast, spot-check."""
    _guard()
    project = _project_by_code(db, project_code)
    event = db.query(OutdoorEvent).filter(OutdoorEvent.project_id == project.id) \
        .order_by(OutdoorEvent.scheduled_at.desc()).first()
    if event is None or event.status in ("completed", "cancelled"):
        event = event_svc.register_event(
            db, org_id=project.org_id, actor=user, title="Village distribution camp",
            lat=project.lat + 0.002, lng=project.lng - 0.001,
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=3),
            project_id=project.id,
        )
    org = db.get(Organization, event.org_id)
    step = "registered"
    if event.status == "registered":
        event_svc.approve_event(db, event=event, actor=user)
        step = "approved"
    if event.status == "approved":
        event_svc.broadcast_location(db, event=event, actor=user,
                                     lat=project.lat, lng=project.lng)
        step = "broadcast"
    inspection = None
    try:
        insp, event_row, dispatch_rec = pick_and_assign(
            db, project=project, actor=user, kind="spot_check",
            outdoor_event=event,
            reason=f"Event-day spot check for {event.code}",
        )
        event.spot_inspection_id = insp.id
        db.commit()
        inspection = {"id": insp.id, "code": insp.code,
                      "inspector_id": insp.assigned_inspector_id,
                      "rationale": dispatch_rec.rationale}
    except ValueError as exc:  # noqa: BLE001
        db.commit()
        inspection = {"error": str(exc)}
    return {
        "event_code": event.code, "step": step,
        "org": org.name if org else None,
        "scheduled_at": event.scheduled_at.isoformat(),
        "lat": event.lat, "lng": event.lng,
        "inspection": inspection,
    }
