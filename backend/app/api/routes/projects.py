"""Project registry (FR-01). Object-level checks on every route."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.audit import audit
from app.core.rbac import (
    CurrentUser, Db, DosjeUser, can_access_project, scope_projects,
)
from app.core.geofence import validate_lat_lng
from app.models.cv import Camera, CctvEvent
from app.models.ops import Alert, Inspection, Project, QrCode
from app.schemas.serializers import project_public

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    org_id: int
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=200)
    scheme: str = Field(min_length=2, max_length=200)
    category: str = Field(pattern="^(centre|distribution|outdoor|skill)$")
    description: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=400)
    lat: float
    lng: float
    geofence_radius_m: float = Field(default=50.0, ge=5, le=2000)
    reported_beneficiaries: int = Field(default=0, ge=0)
    operational_hours: str | None = Field(default=None, max_length=60)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=400)
    geofence_radius_m: float | None = Field(default=None, ge=5, le=2000)
    reported_beneficiaries: int | None = Field(default=None, ge=0)
    operational_hours: str | None = Field(default=None, max_length=60)


def _with_stats(db, project: Project, role: str) -> dict:
    from app.models.users import Organization
    org = db.get(Organization, project.org_id)
    camera_count = db.query(Camera).filter(Camera.project_id == project.id).count()
    open_alerts = db.query(Alert).filter(
        Alert.project_id == project.id,
        Alert.status.in_(("open", "in_review", "verifying", "action_taken"))).count()
    return project_public(project, for_role=role, org_name=org.name if org else None,
                          camera_count=camera_count, open_alerts=open_alerts)


@router.get("")
def list_projects(db: Db, user: CurrentUser,
                  q: str | None = Query(default=None, max_length=100),
                  risk: str | None = Query(default=None, pattern="^(green|amber|red)$")):
    projects = scope_projects(user, db)
    if q:
        needle = q.lower()
        projects = [p for p in projects if needle in p.name.lower()
                    or needle in p.code.lower() or needle in (p.scheme or "").lower()]
    if risk:
        projects = [p for p in projects if p.risk_status == risk]
    return {"projects": [_with_stats(db, p, user.role) for p in projects]}


@router.post("")
def create_project(body: ProjectIn, db: Db, user: DosjeUser):
    if not validate_lat_lng(body.lat, body.lng):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid coordinates")
    existing = db.query(Project).filter(Project.code == body.code.upper()).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Project code already exists")
    project = Project(
        org_id=body.org_id, code=body.code.upper(), name=body.name,
        scheme=body.scheme, category=body.category, description=body.description,
        address=body.address, lat=body.lat, lng=body.lng,
        geofence_radius_m=body.geofence_radius_m,
        reported_beneficiaries=body.reported_beneficiaries,
        operational_hours=body.operational_hours,
    )
    db.add(project)
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="project_created",
          object_type="project", object_id=project.code, commit=False)
    db.commit()
    return _with_stats(db, project, user.role)


@router.get("/{project_id}")
def get_project(project_id: int, db: Db, user: CurrentUser):
    project = db.get(Project, project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return _with_stats(db, project, user.role)


@router.patch("/{project_id}")
def update_project(project_id: int, body: ProjectPatch, db: Db, user: DosjeUser):
    project = db.get(Project, project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="project_updated",
          object_type="project", object_id=project.code,
          detail={"fields": list(body.model_dump(exclude_unset=True))}, commit=False)
    db.commit()
    return _with_stats(db, project, user.role)


@router.get("/{project_id}/overview")
def project_overview(project_id: int, db: Db, user: CurrentUser):
    """Operational overview for a single project (map panel / registry detail)."""
    project = db.get(Project, project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    recent_events = db.query(CctvEvent).filter(CctvEvent.project_id == project.id)\
        .order_by(CctvEvent.ts.desc()).limit(20).all()
    from app.schemas.serializers import cctv_event_public
    q = db.query(QrCode).filter(QrCode.project_id == project.id,
                                QrCode.status == "consumed").count()
    return {
        "project": _with_stats(db, project, user.role),
        "reported_beneficiaries": project.reported_beneficiaries,
        "qr_consumed_total": q,
        "recent_cctv": [cctv_event_public(e) for e in recent_events],
        "inspections": db.query(Inspection).filter(Inspection.project_id == project.id)
            .order_by(Inspection.created_at.desc()).limit(10).count(),
    }
