"""Immutable-style audit trail for security- and evidence-relevant actions."""
from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import IdMixin, TimestampMixin, utcnow


class AuditEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_object", "object_type", "object_id"),
        Index("ix_audit_ts", "ts"),
    )

    ts: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)  # noqa: F821
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(60), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
