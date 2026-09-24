"""Outdoor events (FR-13, scenario C): 48-h GPS registration, approvals, spot-checks."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.audit import audit
from app.core.geofence import validate_lat_lng
from app.core.rbac import Db, DosjeUser, GovernmentUser, require_roles
from app.models.ops import Inspection, OutdoorEvent, Project
from app.models.users import Organization, User
from app.schemas.serializers import outdoor_event_public
from app.services import events as event_svc

router = APIRouter(prefix="/api/events", tags=["events"])

NgoOrGov = Annotated[User, Depends(require_roles("ngo", "dosje", "state"))]
Gov = Annotated[User, Depends(require_roles("dosje", "state"))]


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=400)
    lat: float
    lng: float
    scheduled_at: datetime
    project_id: int | None = None
    org_id: int | None = None  # required for government users registering on behalf


class BroadcastIn(BaseModel):
    lat: float
    lng: float


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=1000)


def _event_or_404(db, event_id: int, user) -> OutdoorEvent:
    ev = db.get(OutdoorEvent, event_id)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    org = db.get(Organization, ev.org_id)
    if user.role == "ngo":
        if ev.org_id != user.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    elif user.role == "state":
        if org is None or org.state_code != user.state_code:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    return ev


@router.post("")
def register(body: EventIn, db: Db, user: NgoOrGov):
    if not validate_lat_lng(body.lat, body.lng):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid coordinates")
    org_id = user.org_id if user.role == "ngo" else body.org_id
    if org_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="org_id required")
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    if body.project_id:
        project = db.get(Project, body.project_id)
        if project is None or (user.role == "ngo" and project.org_id != user.org_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    try:
        ev = event_svc.register_event(
            db, org_id=org_id, actor=user, title=body.title, lat=body.lat,
            lng=body.lng, scheduled_at=body.scheduled_at, address=body.address,
            description=body.description, project_id=body.project_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return outdoor_event_public(ev, org_name=org.name if org else None)


@router.get("")
def list_events(db: Db, user: NgoOrGov):
    q = db.query(OutdoorEvent).order_by(OutdoorEvent.scheduled_at.desc())
    rows = q.limit(200).all()
    visible = []
    orgs = {o.id: o.name for o in db.query(Organization).all()}
    for ev in rows:
        if user.role == "ngo" and ev.org_id != user.org_id:
            continue
        if user.role == "state":
            org = db.get(Organization, ev.org_id)
            if org is None or org.state_code != user.state_code:
                continue
        visible.append(ev)
    return {"events": [outdoor_event_public(e, org_name=orgs.get(e.org_id)) for e in visible]}


@router.get("/{event_id}")
def get_event(event_id: int, db: Db, user: NgoOrGov):
    ev = _event_or_404(db, event_id, user)
    org = db.get(Organization, ev.org_id)
    return outdoor_event_public(ev, org_name=org.name if org else None)


@router.post("/{event_id}/approve")
def approve(event_id: int, body: NoteIn, db: Db, user: Gov):
    ev = _event_or_404(db, event_id, user)
    try:
        ev = event_svc.approve_event(db, event=ev, actor=user, note=body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return outdoor_event_public(ev)


@router.post("/{event_id}/cancel")
def cancel(event_id: int, body: NoteIn, db: Db, user: NgoOrGov):
    ev = _event_or_404(db, event_id, user)
    try:
        ev = event_svc.cancel_event(db, event=ev, actor=user, reason=body.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return outdoor_event_public(ev)


@router.post("/{event_id}/broadcast")
def broadcast(event_id: int, body: BroadcastIn, db: Db, user: NgoOrGov):
    ev = _event_or_404(db, event_id, user)
    try:
        ev = event_svc.broadcast_location(db, event=ev, actor=user,
                                          lat=body.lat, lng=body.lng)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT if isinstance(exc, ValueError)
                            else status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return outdoor_event_public(ev)


@router.post("/{event_id}/spot-check")
def spot_check(event_id: int, db: Db, user: GovernmentUser):
    """Random spot-check dispatch for an outdoor event (event-day verification)."""
    ev = _event_or_404(db, event_id, user)
    project = None
    if ev.project_id:
        project = db.get(Project, ev.project_id)
    if project is None:
        # Standalone event: treat the event pin as the geofence centre.
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Event has no project; assign one to enable dispatch")
    from app.services.dispatch import random_spot_check
    try:
        inspection, event_row, dispatch_rec = random_spot_check(
            db, project=project, actor=user, outdoor_event=ev,
            reason=f"Event-day spot check for {ev.code}",
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    ev.spot_inspection_id = inspection.id
    db.commit()
    return {
        "inspection_id": inspection.id, "code": inspection.code,
        "status": inspection.status, "inspector_id": inspection.assigned_inspector_id,
        "rationale": dispatch_rec.rationale,
    }


@router.post("/{event_id}/complete")
def complete(event_id: int, db: Db, user: Gov):
    ev = _event_or_404(db, event_id, user)
    try:
        ev = event_svc.complete_event(db, event=ev, actor=user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return outdoor_event_public(ev)


@router.post("/{event_id}/flag")
def flag(event_id: int, body: NoteIn, db: Db, user: Gov):
    ev = _event_or_404(db, event_id, user)
    ev = event_svc.flag_event(db, event=ev, actor=user, note=body.note)
    return outdoor_event_public(ev)
