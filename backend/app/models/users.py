"""Identity models: users (role-based), organizations, refresh tokens."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.common import IdMixin, ROLES, TimestampMixin, utcnow
from app.db import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.ops import Inspection


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ngo | institute | gov
    reg_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="org")
    projects: Mapped[list["Project"]] = relationship(back_populates="org")  # noqa: F821


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_role", "role"), Index("ix_users_org", "org_id"))

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # Supabase Auth user id, when Supabase Auth is enabled (nullable in local mode).
    supabase_uid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # constrained in ROLES
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    state_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Optional demo flag used to simulate a Play-Integrity-verifiable device.
    demo_device_ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Last known position (updated by the inspector heartbeat) — used for dispatch.
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_position_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    org: Mapped["Organization | None"] = relationship(back_populates="users")
    inspections: Mapped[list["Inspection"]] = relationship(back_populates="inspector")  # noqa: F821

    @property
    def is_government(self) -> bool:
        return self.role in ("dosje", "state")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.role} {self.email}>"


class RefreshToken(IdMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
