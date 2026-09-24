"""Audit-trail helper. Never log passwords, tokens or secret values."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent

# Actions we log: authentication events, authz failures, admin actions,
# assignment events, evidence access, report generation, security events.
SENSITIVE_OBJECTS = {"evidence", "case", "report", "project", "user", "alert", "assignment"}


def audit(
    db: Session,
    *,
    actor_id: int | None,
    actor_role: str | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    detail: dict | None = None,
    ip: str | None = None,
    commit: bool = True,
) -> AuditEvent:
    entry = AuditEvent(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        ip=ip,
        detail=_sanitize(detail or {}),
    )
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()
    return entry


def _sanitize(detail: dict) -> dict:
    """Drop anything that could carry a secret before it is persisted."""
    blocked = ("password", "token", "secret", "authorization", "api_key")
    return {k: v for k, v in detail.items() if not any(b in k.lower() for b in blocked)}
