"""Field-operations models: inspections/evidence/alerts/cases/QR/events."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import (
    ALERT_OPEN, EVID_LIVE, EVT_REGISTERED, IdMixin, INSP_ASSIGNED,
    QR_ISSUED, TimestampMixin, utcnow,
)
from app.models.registry import Project  # re-export: most modules expect it here

if TYPE_CHECKING:  # pragma: no cover
    from app.models.users import Organization, User


# ---------------------------------------------------------------------------
# Inspections & field flow
# ---------------------------------------------------------------------------

class Inspection(IdMixin, TimestampMixin, Base):
    __tablename__ = "inspections"
    __table_args__ = (Index("ix_inspections_project", "project_id"),
                      Index("ix_inspections_inspector", "assigned_inspector_id"))

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    assigned_inspector_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assignment_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # random_surge | risk_priority | spot_check | scheduled | recheck
    trigger_alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    outdoor_event_id: Mapped[int | None] = mapped_column(ForeignKey("outdoor_events.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=INSP_ASSIGNED, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Blind-envelope: task specifics hidden until activation by the assigned inspector.
    blind_until_activation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    activation_nonce: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commitment_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    lat: Mapped[float | None] = mapped_column(Float, nullable=True)  # project location snapshot
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_radius_m: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    risk_signal_before: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(3000), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    verification_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    route_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    inspector: Mapped["User"] = relationship(back_populates="inspections", foreign_keys=[assigned_inspector_id])
    project: Mapped["Project"] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="inspection")
    locations: Mapped[list["InspectionLocation"]] = relationship(
        back_populates="inspection", order_by="InspectionLocation.ts"
    )


class InspectionLocation(IdMixin, TimestampMixin, Base):
    """GPS heartbeat during an inspection — feeds route-integrity correlation."""
    __tablename__ = "inspection_locations"
    __table_args__ = (Index("ix_loc_inspection_ts", "inspection_id", "ts"),)

    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    within_geofence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    device: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # device-integrity signals

    inspection: Mapped["Inspection"] = relationship(back_populates="locations")


class AssignmentEvent(IdMixin, TimestampMixin, Base):
    """Cryptographically auditable randomization record for every assignment."""
    __tablename__ = "assignment_events"

    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)  # random | risk_hybrid | direct
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    commitment: Mapped[str] = mapped_column(String(64), nullable=False)
    pool_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_signal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    random_priority: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    final_priority: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    candidate_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DeviceCheck(IdMixin, TimestampMixin, Base):
    """Pre-activation device-integrity / anti-spoof verdict (server side)."""
    __tablename__ = "device_checks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    signals: Mapped[dict] = mapped_column(JSON, nullable=False)
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)  # pass | fail | unknown
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ---------------------------------------------------------------------------
# Evidence chain-of-custody
# ---------------------------------------------------------------------------

class Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_inspection", "inspection_id"),
                      Index("ix_evidence_case", "case_id"))

    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # photo | video | frame | document
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    mime: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain_prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # server-generated
    source: Mapped[str] = mapped_column(String(30), default=EVID_LIVE, nullable=False)
    client_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    geofence_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # `metadata` is a reserved name in SQLAlchemy Declarative — attribute is
    # artifact_meta, DB column stays `metadata`.
    artifact_meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    inspection: Mapped["Inspection | None"] = relationship(back_populates="evidence")
    case: Mapped["Case | None"] = relationship(back_populates="evidence")  # noqa: F821


# ---------------------------------------------------------------------------
# Alerts, cases & feedback
# ---------------------------------------------------------------------------

class Alert(IdMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_project", "project_id"),
                      Index("ix_alerts_status", "status"), Index("ix_alerts_kind", "kind"))

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), default="warning", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)

    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    location: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {lat,lng,address}
    signals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # contributing signals
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_signal: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=ALERT_OPEN, nullable=False)
    status_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)  # TP/FP/inconclusive
    feedback_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    case: Mapped["Case | None"] = relationship(back_populates="alerts")


class Case(IdMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (Index("ix_cases_project", "project_id"),)

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(3000), default="", nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    opened_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    closure_action: Mapped[str | None] = mapped_column(String(200), nullable=True)  # escalate|penalty|clear|refer

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="case")


# ---------------------------------------------------------------------------
# QR distribution lifecycle
# ---------------------------------------------------------------------------

class Distribution(IdMixin, TimestampMixin, Base):
    __tablename__ = "distributions"

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    distribution_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # draft|active|closed
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    qr_codes: Mapped[list["QrCode"]] = relationship(back_populates="distribution")


class QrCode(IdMixin, TimestampMixin, Base):
    __tablename__ = "qr_codes"
    __table_args__ = (Index("ix_qr_distribution", "distribution_id"),
                      Index("ix_qr_status", "status"))

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    distribution_id: Mapped[int] = mapped_column(ForeignKey("distributions.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    serial: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=QR_ISSUED, nullable=False)
    recipient_token: Mapped[str | None] = mapped_column(String(120), nullable=True)  # beneficiary ref
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    consumed_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    consumed_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    distribution: Mapped["Distribution"] = relationship(back_populates="qr_codes")


class QrScanLog(IdMixin, TimestampMixin, Base):
    __tablename__ = "qr_scan_logs"
    __table_args__ = (Index("ix_qrlog_code", "code_id"),)

    # Nullable: a scan of an unknown code is logged without a code reference.
    code_id: Mapped[int | None] = mapped_column(ForeignKey("qr_codes.id"), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)  # success|consumed|not_found|wrong_project|void
    scanned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


# ---------------------------------------------------------------------------
# Outdoor events
# ---------------------------------------------------------------------------

class OutdoorEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "outdoor_events"
    __table_args__ = (Index("ix_oevents_org", "org_id"),)

    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=EVT_REGISTERED, nullable=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    live_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_broadcast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    spot_inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    org: Mapped["Organization"] = relationship()


# ---------------------------------------------------------------------------
# Dispatch & end-of-day reports
# ---------------------------------------------------------------------------

class DispatchRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "dispatch_records"

    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False)  # radius_m, method, workload cap
    candidates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), default="", nullable=False)


class EodReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "eod_reports"

    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="all", nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
