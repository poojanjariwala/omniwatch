"""Evidence console APIs: metadata, integrity verification, authorized downloads."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.rbac import CurrentUser, Db, can_access_project
from app.models.ops import Case, Evidence, Inspection, Project
from app.models.users import User
from app.schemas.serializers import evidence_public
from app.services.evidence import resolve_storage_path, verify_artifact

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


def _evidence_for_user(db: Session, user: User, evidence_id: int) -> Evidence:
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    if user.role == "ngo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    if user.role == "pmu":
        # Field inspectors are not NGO staff (org_id is typically NULL): access
        # follows their inspection assignment, with org match as a fallback.
        ok = False
        if ev.inspection_id:
            insp = db.get(Inspection, ev.inspection_id)
            ok = insp is not None and insp.assigned_inspector_id == user.id
        if not ok and user.org_id is not None and ev.project_id:
            project = db.get(Project, ev.project_id)
            ok = project is not None and project.org_id == user.org_id
        if not ok:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return ev
    if ev.project_id:
        project = db.get(Project, ev.project_id)
        if project is not None and not can_access_project(user, project):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return ev


def _log_access(db: Session, actor: User, ev: Evidence, action: str) -> None:
    audit(db, actor_id=actor.id, actor_role=actor.role, action=action,
          object_type="evidence", object_id=str(ev.id),
          detail={"inspection": ev.inspection_id, "case": ev.case_id}, commit=True)


@router.get("/{evidence_id}")
def evidence_detail(evidence_id: int, db: Db, user: CurrentUser):
    ev = _evidence_for_user(db, user, evidence_id)
    integrity = verify_artifact(db, ev)
    _log_access(db, user, ev, "evidence_viewed")
    return {"evidence": evidence_public(ev), "integrity": integrity}


@router.get("/{evidence_id}/file")
def evidence_file(evidence_id: int, db: Db, user: CurrentUser):
    ev = _evidence_for_user(db, user, evidence_id)
    path = resolve_storage_path(db, ev)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Stored file missing")
    _log_access(db, user, ev, "evidence_downloaded")
    # Authorized downloads only; never static file serving. Server filename.
    return Response(
        content=path.read_bytes(),
        media_type=ev.mime,
        headers={
            "Content-Disposition": f'inline; filename="evidence-{ev.id}-{ev.sha256[:12]}{path.suffix}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{evidence_id}/verify")
def verify(evidence_id: int, db: Db, user: CurrentUser):
    ev = _evidence_for_user(db, user, evidence_id)
    integrity = verify_artifact(db, ev)
    _log_access(db, user, ev, "evidence_integrity_checked")
    return integrity


@router.get("")
def list_evidence(db: Db, user: CurrentUser,
                  inspection_id: int | None = None,
                  case_id: int | None = None,
                  limit: int = 100):
    if user.role == "ngo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    q = db.query(Evidence).order_by(Evidence.id.desc())
    if inspection_id:
        q = q.filter(Evidence.inspection_id == inspection_id)
    if case_id:
        case = db.get(Case, case_id)
        project = db.get(Project, case.project_id) if case and case.project_id else None
        if case is None or (user.role != "dosje" and not can_access_project(user, project)):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")
        q = q.filter(Evidence.case_id == case_id)
    rows = q.limit(min(limit, 300)).all()
    visible = []
    for ev in rows:
        if ev.project_id:
            project = db.get(Project, ev.project_id)
            if project is not None and not can_access_project(user, project):
                continue
        if user.role == "pmu" and ev.inspection_id:
            insp = db.get(Inspection, ev.inspection_id)
            if insp is None or insp.assigned_inspector_id != user.id:
                continue
        visible.append(ev)
    return {"evidence": [evidence_public(ev) for ev in visible]}
