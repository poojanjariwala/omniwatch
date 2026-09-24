"""CCTV ingestion models: cameras, occupancy events, adaptive baselines."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.common import IdMixin, TimestampMixin
from app.db import Base


class Camera(IdMixin, TimestampMixin, Base):
    __tablename__ = "cameras"
    __table_args__ = (Index("ix_cameras_project", "project_id"),)

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # file | rtsp | rtmp | mjpeg | simulator
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    ingest_every_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    last_ingest_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_frame_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="cameras")  # noqa: F821
    events: Mapped[list["CctvEvent"]] = relationship(back_populates="camera")  # noqa: F821


class CctvEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "cctv_events"
    __table_args__ = (
        Index("ix_cctv_project_ts", "project_id", "ts"),
        Index("ix_cctv_camera_ts", "camera_id", "ts"),
    )

    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    occupancy: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_handed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # LineZone tripwire count
    window_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    processed_by: Mapped[str] = mapped_column(String(30), default="simulator", nullable=False)
    samples: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # sparse per-frame trace

    camera: Mapped["Camera"] = relationship(back_populates="events")
    project: Mapped["Project"] = relationship()  # noqa: F821


class Baseline(IdMixin, TimestampMixin, Base):
    """Per-project adaptive baseline (EWMA of observed activity).

    Updated in the background ingestion path so a one-off false alarm cannot
    poison the reference; alert decisions compare against this rolling value.
    """
    __tablename__ = "baselines"
    __table_args__ = (Index("ix_baselines_project", "project_id", unique=True),)

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    ewma: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ewma_items: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
