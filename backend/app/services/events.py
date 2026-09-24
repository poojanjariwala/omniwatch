"""Outdoor event workflow (FR-13, scenario C): 48-hour GPS registration + spot checks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models.common import (
    EVT_ACTIVE, EVT_APPROVED, EVT_CANCELLED, EVT_COMPLETED, EVT_FLAGGED,
    EVT_REGISTERED, utcnow,
)
from app.models.ops import OutdoorEvent
from app.models.users import User
from app.services.codes import gen_event_code

ADVANCE_HOURS = 48


def register_event(
    db: Session, *, org_id: int, actor: User, title: str,
    lat: float, lng: float, scheduled_at: datetime,
    address: str | None = None, description: str | None = None,
    project_id: int | None = None,
) -> OutdoorEvent:
    """Register an off-site distribution at least 48 hours in advance."""
    now = utcnow()
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    lead = scheduled_at - now
    if lead < timedelta(hours=ADVANCE_HOURS) and actor.role != "dosje":
        raise ValueError(
            f"Outdoor events must be registered at least {ADVANCE_HOURS} hours in advance "
            f"({lead.total_seconds() / 3600:.1f} h lead time given)")
    event = OutdoorEvent(
        code=gen_event_code(),
        org_id=org_id,
        project_id=project_id,
        title=title,
        description=description,
        address=address,
        lat=lat, lng=lng,
        scheduled_at=scheduled_at,
        status=EVT_REGISTERED,
        created_by=actor.id,
    )
    db.add(event)
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_registered",
          object_type="outdoor_event", object_id=event.code,
          detail={"scheduled_at": scheduled_at.isoformat(), "lat": lat, "lng": lng},
          commit=False)
    db.commit()
    return event


def approve_event(db: Session, *, event: OutdoorEvent, actor: User,
                  note: str = "") -> OutdoorEvent:
    if event.status not in (EVT_REGISTERED,):
        raise ValueError(f"Cannot approve event in status {event.status}")
    event.status = EVT_APPROVED
    event.approved_by = actor.id
    event.approved_at = utcnow()
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_approved",
          object_type="outdoor_event", object_id=event.code, detail={"note": note},
          commit=False)
    db.commit()
    return event


def cancel_event(db: Session, *, event: OutdoorEvent, actor: User, reason: str) -> OutdoorEvent:
    if event.status in (EVT_COMPLETED, EVT_CANCELLED):
        raise ValueError("Event already finished or cancelled")
    event.status = EVT_CANCELLED
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_cancelled",
          object_type="outdoor_event", object_id=event.code, detail={"reason": reason},
          commit=False)
    db.commit()
    return event


def broadcast_location(db: Session, *, event: OutdoorEvent, actor: User,
                       lat: float, lng: float) -> OutdoorEvent:
    """NGO broadcasts the live event location on the event day (geo-live proof)."""
    if event.org_id != actor.org_id and actor.role != "dosje":
        raise PermissionError("Only the organising NGO may broadcast this event location")
    if event.status != EVT_APPROVED:
        raise ValueError("Event not yet approved for broadcast")
    event.live_lat, event.live_lng = lat, lng
    event.last_broadcast_at = utcnow()
    if event.status == EVT_APPROVED:
        event.status = EVT_ACTIVE
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_broadcast",
          object_type="outdoor_event", object_id=event.code,
          detail={"lat": lat, "lng": lng}, commit=False)
    db.commit()
    return event


def complete_event(db: Session, *, event: OutdoorEvent, actor: User) -> OutdoorEvent:
    event.status = EVT_COMPLETED
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_completed",
          object_type="outdoor_event", object_id=event.code, commit=False)
    db.commit()
    return event


def flag_event(db: Session, *, event: OutdoorEvent, actor: User,
               note: str) -> OutdoorEvent:
    event.status = EVT_FLAGGED
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="outdoor_event_flagged",
          object_type="outdoor_event", object_id=event.code, detail={"note": note},
          commit=False)
    db.commit()
    return event
