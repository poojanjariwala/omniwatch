"""Case workflow (FR-16): alert → review → inspection → verification → closure."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.core.audit import audit
from app.core.timeutil import parse_iso_utc
from app.core.rbac import (
    Db, DosjeUser, GovernmentUser, SensitiveUser, can_access_project, require_roles,
)
from app.models.ops import Alert, Case, Evidence, Inspection, Project
from app.models.common import utcnow
from app.models.users import User
from app.schemas.serializers import (
    alert_public, case_public, evidence_public, inspection_full,
)
from app.services import alerts as alert_svc
from app.services.evidence import EVID_OFFICIAL, store_evidence
from app.services.reports import case_dossier

router = APIRouter(prefix="/api/cases", tags=["cases"])

GovPmu = Annotated[User, Depends(require_roles("dosje", "state", "pmu"))]
Officials = Annotated[User, Depends(require_roles("dosje", "state"))]


def _case_or_404(db, case_id: int, user: User) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")
    if user.role not in ("dosje", "state", "pmu"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    project = db.get(Project, case.project_id) if case.project_id else None
    if project is not None and not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _serialize_case(db, case: Case) -> dict:
    project = db.get(Project, case.project_id) if case.project_id else None
    return case_public(
        case,
        project_name=project.name if project else None,
        alert_count=db.query(Alert).filter(Alert.case_id == case.id).count(),
        evidence_count=db.query(Evidence).filter(Evidence.case_id == case.id).count(),
        inspection_count=(db.query(Inspection)
                          .filter(Inspection.project_id == case.project_id).count()
                          if case.project_id else 0),
    )


@router.get("")
def list_cases(db: Db, user: GovernmentUser):
    rows = db.query(Case).order_by(Case.opened_at.desc()).limit(200).all()
    out = []
    for c in rows:
        project = db.get(Project, c.project_id) if c.project_id else None
        if project is not None and not can_access_project(user, project):
            continue
        out.append(_serialize_case(db, c))
    return {"cases": out}


@router.post("")
def open_case(alert_id: int, db: Db, user: DosjeUser, note: str = ""):
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if alert.case_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Alert already in a case")
    case = alert_svc.open_case(db, alert=alert, actor_id=user.id, note=note)
    audit(db, actor_id=user.id, actor_role=user.role, action="case_opened",
          object_type="case", object_id=case.code, detail={"alert": alert.code},
          commit=False)
    db.commit()
    return {"case_id": case.id, "case_code": case.code}


@router.get("/{case_id}")
def get_case(case_id: int, db: Db, user: GovPmu):
    case = _case_or_404(db, case_id, user)
    project = db.get(Project, case.project_id) if case.project_id else None
    alerts = db.query(Alert).filter(Alert.case_id == case.id)\
        .order_by(Alert.occurred_at).all()
    evidence = db.query(Evidence).filter(Evidence.case_id == case.id)\
        .order_by(Evidence.id).all()
    inspections = []
    if case.project_id:
        for insp in db.query(Inspection).filter(Inspection.project_id == case.project_id)\
                .order_by(Inspection.created_at).all():
            inspector = db.get(User, insp.assigned_inspector_id)
            inspections.append(inspection_full(insp, project=project, inspector=inspector))
    timeline = []
    for a in alerts:
        timeline.append({"at": a.occurred_at.isoformat(), "kind": "alert",
                         "ref": a.code, "text": a.title, "status": a.status})
    for e in evidence:
        timeline.append({"at": e.captured_at.isoformat(), "kind": "evidence",
                         "ref": f"ev-{e.id}", "text": f"{e.kind} evidence added",
                         "sha256": e.sha256[:16]})
    for i in inspections:
        timeline.append({"at": i.created_at.isoformat(), "kind": "inspection",
                         "ref": i.code, "text": f"Inspection {i.code} ({i.status})"})
    timeline.sort(key=lambda t: t["at"] or "")
    return {
        "case": _serialize_case(db, case),
        "alerts": [alert_public(a, project_name=project.name if project else None)
                   for a in alerts],
        "inspections": inspections,
        "evidence": [evidence_public(e) for e in evidence],
        "timeline": timeline,
    }


class CloseIn(BaseModel):
    closure_action: str = Field(default="clear",
                                pattern="^(escalate|penalty|clear|refer)$")
    closure_note: str = Field(default="", max_length=2000)


@router.post("/{case_id}/close")
def close_case(case_id: int, body: CloseIn, db: Db, user: SensitiveUser):
    """Human-only closure of a case (requires re-authentication token)."""
    if user.role not in ("dosje", "state"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Officials only")
    case = _case_or_404(db, case_id, user)
    if case.status == "closed":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Case already closed")
    case.status = "closed"
    case.closed_by = user.id
    case.closed_at = utcnow()
    case.closure_action = body.closure_action
    case.closure_note = body.closure_note
    for alert in db.query(Alert).filter(Alert.case_id == case.id,
                                        Alert.status != "closed").all():
        try:
            alert_svc.transition_alert(db, alert, "closed", actor_id=user.id,
                                       note=f"Case {case.code} {body.closure_action}")
        except ValueError:
            pass
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="case_closed",
          object_type="case", object_id=case.code,
          detail={"closure_action": body.closure_action}, commit=False)
    db.commit()
    return {"case_code": case.code, "status": "closed",
            "closure_action": body.closure_action}


@router.post("/{case_id}/evidence")
def attach_evidence(case_id: int, db: Db, user: GovPmu,
                    file: UploadFile, kind: str = "photo",
                    captured_at: str | None = None,
                    lat: float | None = None, lng: float | None = None):
    """Government reviewer attaches corroborating material to a case."""
    case = _case_or_404(db, case_id, user)
    if kind not in ("photo", "video", "document"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="kind must be photo, video or document")
    captured = None
    if captured_at:
        try:
            captured = parse_iso_utc(captured_at)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="captured_at must be an ISO-8601 timestamp") from exc
    data = file.file.read(60 * 1024 * 1024 + 1)
    try:
        evidence = store_evidence(
            db, actor=user, data=data,
            declared_mime=file.content_type or "application/octet-stream",
            kind=kind,
            captured_at=captured,
            lat=lat, lng=lng, source=EVID_OFFICIAL, case=case,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return evidence_public(evidence)


@router.get("/{case_id}/report")
def report_dossier(case_id: int, db: Db, user: SensitiveUser):
    """Evidence-backed PDF dossier (FR-15) with SHA-256 + chain block."""
    if user.role not in ("dosje", "state"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Officials only")
    case = _case_or_404(db, case_id, user)
    path, sha = case_dossier(db, case, actor_name=user.full_name)
    audit(db, actor_id=user.id, actor_role=user.role, action="report_generated",
          object_type="case", object_id=case.code,
          detail={"file": path.name, "sha256": sha}, commit=True)
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{path.name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "X-Report-SHA256": sha,
        },
    )
