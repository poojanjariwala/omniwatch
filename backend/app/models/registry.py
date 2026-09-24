"""Project registry model with geo and live risk status."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.common import IdMixin, RISK_GREEN, TimestampMixin, utcnow
from app.db import Base


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_org", "org_id"), Index("ix_projects_risk", "risk_status"))

    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scheme: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)  # centre|distribution|outdoor|skill
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    geofence_radius_m: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    reported_beneficiaries: Mapped[int] = mapped_column(default=0, nullable=False)
    operational_hours: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. 09:00-17:00

    # Live risk state — computed by the anomaly engine; a human decision record
    # must accompany any escalation. NEVER a fraud verdict by itself.
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_status: Mapped[str] = mapped_column(String(10), default=RISK_GREEN, nullable=False)
    risk_last_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_reason: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # explainable summary

    org: Mapped["Organization"] = relationship(back_populates="projects")  # noqa: F821
    cameras: Mapped[list["Camera"]] = relationship(back_populates="project")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project {self.code} {self.name} risk={self.risk_status} {self.risk_score:.2f}>"
