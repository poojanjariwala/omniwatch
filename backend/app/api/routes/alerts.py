"""Alert queue (FR-05 explainable). Government roles only — NGO never sees alerts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sqlalchemy import false

from app.core.audit import audit
from app.core.rbac import Db, DosjeUser, GovernmentUser, can_access_project
from app.models.ops import Alert, Inspection, Project
from app.models.users import Organization
from app.schemas.serializers import alert_public
from app.services import alerts as alert_svc

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class StatusIn(BaseModel):
    to_status: str = Field(pattern="^(open|in_review|verifying|action_taken|closed)$")
    note: str = Field(default="", max_length=2000)


class FeedbackIn(BaseModel):
    feedback: str = Field(pattern="^(true_positive|false_positive|inconclusive)$")
    note: str = Field(default="", max_length=1000)


class CaseIn(BaseModel):
    note: str = Field(default="", max_length=2000)


def _visible_alerts(db, user):
    query = db.query(Alert)
    if user.role == "state":
        org_ids = [o.id for o in db.query(Organization)
                   .filter(Organization.state_code == user.state_code).all()]
        proj_ids = [p.id for p in db.query(Project)
                    .filter(Project.org_id.in_(org_ids) if org_ids else false()).all()]
        query = query.filter(Alert.project_id.in_(proj_ids) if proj_ids else false())
    elif user.role == "pmu":
        # PMU sees alerts for their own assignments and their organisation's projects.
        insp_ids = [i.id for i in db.query(Inspection.id)
                    .filter(Inspection.assigned_inspector_id == user.id).all()]
        org_ids = [p.id for p in db.query(Project.id)
                   .filter(Project.org_id == user.org_id).all()] if user.org_id else []
        conds = []
        if org_ids:
            conds.append(Alert.project_id.in_(org_ids))
        if insp_ids:
            conds.append(Alert.inspection_id.in_(insp_ids))
        if conds:
            from functools import reduce
            from operator import or_
            query = query.filter(reduce(or_, conds))
        else:
            query = query.filter(false())
    return query


def _alert_or_404(db, alert_id: int, user) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if user.role not in ("dosje", "state", "pmu"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    if user.role == "state" and alert.project_id:
        project = db.get(Project, alert.project_id)
        if project is None or not can_access_project(user, project):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


def _with_project_name(db, alert: Alert) -> dict:
    p = db.get(Project, alert.project_id) if alert.project_id else None
    return alert_public(alert, project_name=p.name if p else None)


@router.get("")
def list_alerts(db: Db, user: GovernmentUser,
                kind: str | None = None, severity: str | None = None,
                status_filter: str | None = None, limit: int = 100):
    query = _visible_alerts(db, user).order_by(Alert.occurred_at.desc())
    if kind:
        query = query.filter(Alert.kind == kind)
    if severity:
        query = query.filter(Alert.severity == severity)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    alerts = query.limit(min(limit, 500)).all()
    return {"alerts": [_with_project_name(db, a) for a in alerts]}


@router.get("/{alert_id}")
def get_alert(alert_id: int, db: Db, user: GovernmentUser):
    alert = _alert_or_404(db, alert_id, user)
    out = _with_project_name(db, alert)
    return out


@router.patch("/{alert_id}/status")
def change_status(alert_id: int, body: StatusIn, db: Db, user: GovernmentUser):
    alert = _alert_or_404(db, alert_id, user)
    try:
        alert_svc.transition_alert(db, alert, body.to_status,
                                   actor_id=user.id, note=body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit(db, actor_id=user.id, actor_role=user.role, action="alert_status_changed",
          object_type="alert", object_id=alert.code,
          detail={"to": body.to_status, "note": body.note}, commit=False)
    db.commit()
    return _with_project_name(db, alert)


@router.post("/{alert_id}/feedback")
def submit_feedback(alert_id: int, body: FeedbackIn, db: Db, user: DosjeUser):
    """Model feedback loop (TP / FP / inconclusive) — recorded, never automatic."""
    alert = _alert_or_404(db, alert_id, user)
    alert.feedback = body.feedback
    alert.feedback_note = body.note
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="model_feedback",
          object_type="alert", object_id=alert.code,
          detail={"feedback": body.feedback, "note": body.note}, commit=False)
    db.commit()
    return _with_project_name(db, alert)


@router.post("/{alert_id}/case")
def raise_case(alert_id: int, body: CaseIn, db: Db, user: DosjeUser):
    """Escalate an alert into an investigation case (human decision)."""
    alert = _alert_or_404(db, alert_id, user)
    if alert.case_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Alert already in a case")
    case = alert_svc.open_case(db, alert=alert, actor_id=user.id, note=body.note)
    audit(db, actor_id=user.id, actor_role=user.role, action="case_opened",
          object_type="case", object_id=case.code, detail={"alert": alert.code},
          commit=False)
    db.commit()
    return {"case_id": case.id, "case_code": case.code}


def dispatch_alert_inspection(db, alert: Alert, actor) -> None:
    """Hook used by /dispatch and demo runners (single place for the rule)."""
    from app.services.dispatch import pick_and_assign
    project = db.get(Project, alert.project_id) if alert.project_id else None
    if project is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Alert has no project to dispatch to")
    inspection, _, _ = pick_and_assign(
        db, project=project, actor=actor, kind="risk_priority",
        risk_signal=alert.risk_signal,
        trigger_alert_id=alert.id, reason=f"Verification of alert {alert.code}",
    )
    alert.inspection_id = inspection.id
    db.flush()
    alert_svc.transition_alert(db, alert, "verifying",
                               actor_id=actor.id, note="Inspection dispatched")
    db.commit()


class DispatchIn(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.post("/{alert_id}/dispatch")
def dispatch_inspection(alert_id: int, body: DispatchIn, db: Db, user: GovernmentUser):
    """Dispatch a blind inspection to verify this alert."""
    alert = _alert_or_404(db, alert_id, user)
    if alert.project_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No project linked")
    dispatch_alert_inspection(db, alert, user)
    return _with_project_name(db, alert)
