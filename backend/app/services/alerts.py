"""Alert lifecycle helpers — every alert is explainable and human-adjudicated."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models.common import (
    ALERT_ACTION, ALERT_CLOSED, ALERT_IN_REVIEW, ALERT_OPEN, ALERT_VERIFYING,
    RISK_AMBER, RISK_GREEN, RISK_RED, utcnow,
)
from app.models.ops import Alert, Case, Project
from app.services.codes import gen_alert_code


def _bump_history(alert: Alert, note: str, actor: str | None = None) -> None:
    history = list(alert.status_history or [])
    history.append({"status": alert.status, "at": utcnow().isoformat(), "by": actor, "note": note})
    alert.status_history = history


def create_alert(
    db: Session,
    *,
    kind: str,
    severity: str,
    title: str,
    summary: str,
    project: Project | None = None,
    occurred_at: datetime | None = None,
    signals: list | None = None,
    risk_signal: float = 0.0,
    recommended_action: str = "",
    ai_generated: bool = True,
    inspection_id: int | None = None,
    evidence_refs: list | None = None,
    location: dict | None = None,
    actor_id: int | None = None,
) -> Alert:
    alert = Alert(
        code=gen_alert_code(kind),
        kind=kind,
        severity=severity,
        title=title,
        summary=summary,
        project_id=project.id if project else None,
        inspection_id=inspection_id,
        occurred_at=occurred_at or utcnow(),
        signals=list(signals or []),
        evidence_refs=list(evidence_refs or []),
        risk_signal=max(0.0, min(1.0, risk_signal)),
        recommended_action=recommended_action,
        ai_generated=ai_generated,
        location=location or ({"lat": project.lat, "lng": project.lng} if project else None),
    )
    _bump_history(alert, "Alert raised", actor="system" if ai_generated else None)
    db.add(alert)
    db.flush()
    audit(db, actor_id=actor_id, actor_role="system" if ai_generated else None,
          action="alert_created", object_type="alert", object_id=alert.code,
          detail={"kind": kind, "severity": severity, "risk": risk_signal}, commit=False)
    return alert


def update_project_risk(db: Session, project: Project) -> None:
    """Recompute project risk from its most recent open alerts.

    Risk is advisory colouring for officials — never a verdict.
    """
    row = db.query(func.count(Alert.id), func.max(Alert.risk_signal)).filter(
        Alert.project_id == project.id,
        Alert.status.in_((ALERT_OPEN, ALERT_IN_REVIEW, ALERT_VERIFYING, ALERT_ACTION)),
    ).one()
    open_count, max_risk = row
    max_risk = float(max_risk or 0.0)
    project.risk_score = round(max_risk, 3)
    if open_count == 0 or max_risk < 0.4:
        project.risk_status = RISK_GREEN
    elif max_risk < 0.7:
        project.risk_status = RISK_AMBER
    else:
        project.risk_status = RISK_RED
    project.risk_reason = {
        "open_alerts": int(open_count),
        "top_signal": max_risk,
        "updated": utcnow().isoformat(),
    }
    project.risk_last_update = utcnow()


# Allowed status flow: open -> in_review -> verifying -> action_taken -> closed
# (open -> verifying is permitted for the direct "dispatch inspection" path,
# which is an audited official action.)
TRANSITIONS = {
    ALERT_OPEN: (ALERT_IN_REVIEW, ALERT_VERIFYING),
    ALERT_IN_REVIEW: (ALERT_VERIFYING, ALERT_ACTION, ALERT_CLOSED),
    ALERT_VERIFYING: (ALERT_ACTION, ALERT_CLOSED),
    ALERT_ACTION: (ALERT_CLOSED,),
}
VALID_STATUSES = (ALERT_OPEN, ALERT_IN_REVIEW, ALERT_VERIFYING, ALERT_ACTION, ALERT_CLOSED)


def transition_alert(
    db: Session,
    alert: Alert,
    to_status: str,
    *,
    actor_id: int,
    note: str = "",
) -> Alert:
    if to_status not in VALID_STATUSES:
        raise ValueError(f"Unknown alert status: {to_status}")
    allowed = TRANSITIONS.get(alert.status, ())
    if to_status not in allowed:
        raise ValueError(f"Illegal alert transition {alert.status} -> {to_status}")
    alert.status = to_status
    if to_status == ALERT_CLOSED:
        alert.resolved_at = utcnow()
        alert.resolved_by = actor_id
    _bump_history(alert, note or f"Status changed to {to_status}", actor=str(actor_id))
    db.flush()
    return alert


def open_alert_exists(db: Session, *, project_id: int | None, kind: str,
                      minutes: int = 20) -> bool:
    """Cooldown guard so a persistent surge doesn't spam the queue."""
    from app.core.timeutil import as_utc
    cutoff = utcnow()
    recent = (db.query(Alert)
              .filter(Alert.kind == kind, Alert.status == ALERT_OPEN)
              .order_by(Alert.occurred_at.desc())
              .limit(8).all())
    for a in recent:
        if project_id is not None and a.project_id != project_id:
            continue
        occurred = as_utc(a.occurred_at)
        if occurred and (cutoff - occurred).total_seconds() < minutes * 60:
            return True
    return False


def open_case(db: Session, *, alert: Alert, actor_id: int, note: str = "") -> Case:
    case = Case(
        code=gen_alert_code("CASE"),
        title=alert.title,
        description=alert.summary,
        project_id=alert.project_id,
        status="open",
        opened_by=actor_id,
    )
    db.add(case)
    db.flush()
    alert.case_id = case.id
    if note:
        _bump_history(alert, note, actor=str(actor_id))
    db.flush()
    return case
