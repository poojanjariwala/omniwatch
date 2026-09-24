"""QR distribution lifecycle (FR-12 + row D2).

Server-issued codes; a scan consumes the code atomically (UPDATE … WHERE
status='issued'), so concurrent replays are structurally impossible. Duplicate
attempts are logged and raise an explainable alert visible to government roles
only — the NGO never sees the alert.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.randomization import random_hex
from app.models.common import (
    QR_CONSUMED, QR_ISSUED, SEVERITY_CRITICAL, SEVERITY_WARNING, utcnow,
)
from app.models.ops import (
    Alert, Distribution, OutdoorEvent, Project, QrCode, QrScanLog,
)
from app.models.users import User
from app.services import alerts as alert_svc
from app.services.codes import gen_distribution_code


def issue_batch(
    db: Session,
    *,
    project: Project,
    org_id: int,
    actor: User,
    title: str,
    count: int,
    distribution_date: date | None = None,
) -> Distribution:
    if not 1 <= count <= 5000:
        raise ValueError("Batch size must be between 1 and 5000")
    dist = Distribution(
        code=gen_distribution_code(),
        project_id=project.id,
        org_id=org_id,
        title=title,
        distribution_date=distribution_date or date.today(),
        total_items=count,
        status="active",
        created_by=actor.id,
    )
    db.add(dist)
    db.flush()
    for i in range(count):
        db.add(QrCode(
            code=random_hex(16),
            distribution_id=dist.id,
            project_id=project.id,
            serial=i + 1,
            status=QR_ISSUED,
        ))
    audit(db, actor_id=actor.id, actor_role=actor.role, action="qr_batch_issued",
          object_type="distribution", object_id=dist.code,
          detail={"count": count, "project_code": project.code}, commit=False)
    db.commit()
    return dist


def distribution_stats(db: Session, distribution_id: int) -> dict:
    total = db.query(func.count(QrCode.id)).filter(
        QrCode.distribution_id == distribution_id
    ).scalar()
    consumed = db.query(func.count(QrCode.id)).filter(
        QrCode.distribution_id == distribution_id,
        QrCode.status == QR_CONSUMED,
    ).scalar()
    return {"total": int(total or 0), "consumed": int(consumed or 0)}


def _record_scan(db: Session, *, code: QrCode | None, ok: bool, reason: str,
                 actor: User | None, lat: float | None, lng: float | None,
                 detail: dict | None = None) -> None:
    db.add(QrScanLog(
        code_id=code.id if code else None,
        ok=ok,
        reason=reason,
        scanned_by=actor.id if actor else None,
        lat=lat, lng=lng,
        detail=detail or {},
    ))


def scan_code(
    db: Session,
    *,
    actor: User,
    code_str: str,
    lat: float | None = None,
    lng: float | None = None,
    recipient_token: str | None = None,
) -> dict:
    """Validate + consume a QR code atomically. Never auto-accuses anyone."""
    code = db.query(QrCode).filter(QrCode.code == code_str).first()
    if code is None:
        _record_scan(db, code=None, ok=False, reason="not_found", actor=actor,
                     lat=lat, lng=lng)
        db.commit()
        return {"ok": False, "reason": "not_found", "message": "Code not recognised"}

    # NGO may only transact codes under projects of its own organisation.
    if actor.role == "ngo":
        owned = db.query(Project.id).filter(Project.id == code.project_id,
                                            Project.org_id == actor.org_id).first()
        if owned is None:
            _record_scan(db, code=code, ok=False, reason="wrong_project", actor=actor,
                         lat=lat, lng=lng)
            audit(db, actor_id=actor.id, actor_role=actor.role,
                  action="qr_scan_cross_project_denied", object_type="qr_code",
                  object_id=code.code, commit=True)
            return {"ok": False, "reason": "wrong_project",
                    "message": "Code does not belong to your organisation's project"}

    project = db.get(Project, code.project_id)

    # Duplicate-recipient check (simulated biometric/beneficiary binding).
    duplicate_recipient = None
    if recipient_token and code.status == QR_ISSUED:
        earlier = (db.query(QrCode)
                   .filter(QrCode.project_id == code.project_id,
                           QrCode.recipient_token == recipient_token,
                           QrCode.status == QR_CONSUMED,
                           QrCode.consumed_at.isnot(None))
                   .order_by(QrCode.consumed_at.desc()).first())
        if earlier:
            duplicate_recipient = earlier

    if code.status == QR_CONSUMED:
        # Duplicate / replay — blocked, logged, and flagged for government eyes.
        first = code.consumed_at
        signals = [
            {"type": "qr_replay", "code": code.code, "serial": code.serial,
             "distribution": code.distribution_id,
             "first_consumed_at": first.isoformat() if first else None,
             "project": project.code, "scan_lat": lat, "scan_lng": lng},
        ]
        if duplicate_recipient:
            signals.append({"type": "duplicate_recipient",
                            "recipient_token": recipient_token,
                            "previously_consumed": earlier.code})
        _record_scan(db, code=code, ok=False, reason="consumed", actor=actor,
                     lat=lat, lng=lng)
        if not alert_svc.open_alert_exists(db, project_id=code.project_id,
                                           kind="qr_replay", minutes=10):
            risk = 0.55 if duplicate_recipient else 0.45
            alert = alert_svc.create_alert(
                db,
                kind="qr_replay",
                severity=SEVERITY_WARNING,
                title="Reused QR code attempt blocked",
                summary=(f"Item QR #{code.serial} in distribution {code.distribution_id} "
                         f"was scanned again after being consumed at "
                         f"{(first.isoformat() if first else 'unknown')}. The transaction "
                         f"was blocked. Duplicate-recipient signal: "
                         f"{'yes' if duplicate_recipient else 'no'}."),
                project=project,
                signals=signals,
                risk_signal=risk,
                recommended_action=("Check whether items are being recycled; verify the "
                                    "register against CCTV handout footage. Human "
                                    "verification required before any action."),
                ai_generated=True,
                actor_id=actor.id,
            )
            alert_svc.update_project_risk(db, project)
        db.commit()
        return {"ok": False, "reason": "consumed",
                "message": "This item was already handed out — transaction blocked"}

    # Atomic consume: only one concurrent scan can win this update.
    now = utcnow()
    updated = db.execute(
        update(QrCode)
        .where(QrCode.id == code.id, QrCode.status == QR_ISSUED)
        .values(status=QR_CONSUMED, recipient_token=recipient_token,
                consumed_at=now, consumed_by=actor.id, consumed_lat=lat,
                consumed_lng=lng)
    ).rowcount
    if updated != 1:
        _record_scan(db, code=code, ok=False, reason="consumed", actor=actor,
                     lat=lat, lng=lng)
        db.commit()
        return {"ok": False, "reason": "consumed",
                "message": "Item already consumed (concurrent scan)"}

    _record_scan(db, code=code, ok=True, reason="success", actor=actor, lat=lat, lng=lng)
    stats = distribution_stats(db, code.distribution_id)

    if duplicate_recipient is not None and not alert_svc.open_alert_exists(
            db, project_id=code.project_id, kind="duplicate_recipient", minutes=10):
        alert_svc.create_alert(
            db,
            kind="duplicate_recipient",
            severity=SEVERITY_WARNING,
            title="Same recipient served again",
            summary=(f"Recipient token {recipient_token} was recorded against two items "
                     f"({earlier.code} and {code.code}) in a short period at {project.name}."),
            project=project,
            signals=[{"type": "recipient_token", "value": recipient_token},
                     {"type": "items", "first": earlier.code, "second": code.code},
                     {"type": "note",
                      "value": "Simulated beneficiary/biometric binding in this demo."}],
            risk_signal=0.5,
            recommended_action=("Review whether the beneficiary genuinely received a "
                                "second item; verify with CCTV or an inspection."),
            ai_generated=True,
            actor_id=actor.id,
        )
        alert_svc.update_project_risk(db, project)

    db.commit()
    return {
        "ok": True,
        "reason": "success",
        "message": f"Item #{code.serial} recorded as handed out",
        "serial": code.serial,
        "distribution_id": code.distribution_id,
        "distribution_code": code.distribution.code,
        "consumed_today": stats["consumed"],
        "total_items": stats["total"],
        "duplicate_recipient": duplicate_recipient is not None,
    }
