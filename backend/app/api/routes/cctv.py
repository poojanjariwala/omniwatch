"""CCTV configuration + event history (FR-03). Heavy AI runs async in workers."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.audit import audit
from app.core.rbac import CurrentUser, Db, DosjeUser, can_access_project, scope_projects
from app.models.cv import Camera, CctvEvent
from app.models.registry import Project
from app.schemas.serializers import camera_public, cctv_event_public

router = APIRouter(prefix="/api/cctv", tags=["cctv"])


class CameraIn(BaseModel):
    project_id: int
    name: str = Field(min_length=2, max_length=150)
    source_type: str = Field(pattern="^(file|rtsp|rtmp|mjpeg|simulator)$")
    url: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    ingest_every_seconds: int = Field(default=30, ge=5, le=3600)


def _camera_or_404(db, camera_id: int, user) -> Camera:
    cam = db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Camera not found")
    project = db.get(Project, cam.project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return cam


@router.get("")
def list_cameras(db: Db, user: CurrentUser):
    projects = scope_projects(user, db)
    ids = [p.id for p in projects]
    if user.role == "ngo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    cameras = db.query(Camera).filter(Camera.project_id.in_(ids) if ids else False) \
        .order_by(Camera.project_id, Camera.id).all()
    names = {p.id: (p.name, p.code) for p in projects}
    return {"cameras": [
        camera_public(c, project_name=names[c.project_id][0] if c.project_id in names else None,
                      project_code=names[c.project_id][1] if c.project_id in names else None)
        for c in cameras]}


@router.post("")
def create_camera(body: CameraIn, db: Db, user: DosjeUser):
    project = db.get(Project, body.project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    cam = Camera(project_id=body.project_id, name=body.name,
                 source_type=body.source_type, url=body.url,
                 enabled=body.enabled, ingest_every_seconds=body.ingest_every_seconds)
    db.add(cam)
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="camera_created",
          object_type="camera", object_id=str(cam.id),
          detail={"project": project.code, "source_type": cam.source_type}, commit=False)
    db.commit()
    return camera_public(cam)


@router.patch("/{camera_id}")
def update_camera(camera_id: int, body: CameraIn, db: Db, user: DosjeUser):
    cam = _camera_or_404(db, camera_id, user)
    for f in ("name", "source_type", "url", "enabled", "ingest_every_seconds"):
        setattr(cam, f, getattr(body, f))
    db.commit()
    audit(db, actor_id=user.id, actor_role=user.role, action="camera_updated",
          object_type="camera", object_id=str(cam.id), commit=True)
    return camera_public(cam)


@router.post("/{camera_id}/toggle")
def toggle_camera(camera_id: int, db: Db, user: DosjeUser):
    cam = _camera_or_404(db, camera_id, user)
    cam.enabled = not cam.enabled
    db.commit()
    return camera_public(cam)


@router.get("/{camera_id}/events")
def camera_events(camera_id: int, db: Db, user: CurrentUser,
                  limit: int = Query(default=60, ge=1, le=500)):
    if user.role == "ngo":  # consistent with /cctv/events — CCTV is a government surface
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    cam = _camera_or_404(db, camera_id, user)
    events = db.query(CctvEvent).filter(CctvEvent.camera_id == cam.id) \
        .order_by(CctvEvent.ts.desc()).limit(limit).all()
    return {"events": [cctv_event_public(e) for e in events],
            "camera": camera_public(cam)}


@router.post("/{camera_id}/ingest")
def trigger_ingest(camera_id: int, db: Db, user: DosjeUser):
    """Run one ingest cycle now (dev/demo). Production cadence is Celery beat."""
    from app.services.cv.engine import ingest_once
    cam = _camera_or_404(db, camera_id, user)
    result = ingest_once(db, cam, actor_id=user.id)
    audit(db, actor_id=user.id, actor_role=user.role, action="cctv_ingest_manual",
          object_type="camera", object_id=str(cam.id), detail=result, commit=True)
    return result


@router.get("/events")
def recent_events(db: Db, user: CurrentUser,
                  project_id: int | None = None,
                  limit: int = Query(default=100, ge=1, le=500)):
    if user.role == "ngo":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    projects = scope_projects(user, db)
    ids = {p.id for p in projects}
    q = db.query(CctvEvent).order_by(CctvEvent.ts.desc())
    if project_id:
        if project_id not in ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
        q = q.filter(CctvEvent.project_id == project_id)
    elif ids:
        q = q.filter(CctvEvent.project_id.in_(ids))
    events = q.limit(limit).all()
    return {"events": [cctv_event_public(e) for e in events]}
