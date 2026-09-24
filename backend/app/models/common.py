"""Shared model helpers: ID/timestamp mixins and domain enums."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --- Enumerated string constants -------------------------------------------------

ROLE_DOSJE = "dosje"
ROLE_PMU = "pmu"
ROLE_NGO = "ngo"
ROLE_STATE = "state"
ROLE_BENEFICIARY = "beneficiary"
ROLES = (ROLE_DOSJE, ROLE_PMU, ROLE_NGO, ROLE_STATE, ROLE_BENEFICIARY)

ORG_NGO = "ngo"
ORG_INSTITUTE = "institute"
ORG_GOV = "gov"

RISK_GREEN = "green"
RISK_AMBER = "amber"
RISK_RED = "red"

ALERT_KINDS = (
    "activity_surge",        # CCTV crowd/traffic surge vs baseline
    "tip_off",               # pre-inspection tip-off style sudden surge
    "qr_replay",             # duplicate/replayed QR transaction
    "duplicate_recipient",   # same recipient appearing again (face signal / token)
    "geofence_violation",    # evidence or inspector outside allowed zone
    "route_mismatch",        # timestamps out of order / impossible route
    "reconciliation",        # reported vs independently observed mismatch
    "device_integrity",      # failed or missing device-integrity check
    "outdoor_spot",          # outdoor event flagged for spot verification
)
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

ALERT_OPEN = "open"
ALERT_IN_REVIEW = "in_review"
ALERT_VERIFYING = "verifying"
ALERT_ACTION = "action_taken"
ALERT_CLOSED = "closed"
ALERT_STATUSES = (ALERT_OPEN, ALERT_IN_REVIEW, ALERT_VERIFYING, ALERT_ACTION, ALERT_CLOSED)

INSP_CREATED = "created"
INSP_ASSIGNED = "assigned"
INSP_ACTIVATED = "activated"
INSP_IN_PROGRESS = "in_progress"
INSP_SUBMITTED = "submitted"
INSP_COMPLETED = "completed"
INSP_CANCELLED = "cancelled"
INSP_STATUSES = (
    INSP_CREATED, INSP_ASSIGNED, INSP_ACTIVATED, INSP_IN_PROGRESS,
    INSP_SUBMITTED, INSP_COMPLETED, INSP_CANCELLED,
)

QR_ISSUED = "issued"
QR_CONSUMED = "consumed"
QR_VOID = "void"

EVT_REGISTERED = "registered"
EVT_APPROVED = "approved"
EVT_ACTIVE = "active"
EVT_COMPLETED = "completed"
EVT_CANCELLED = "cancelled"
EVT_FLAGGED = "flagged"

EVID_LIVE = "live_camera"
EVID_DEMO_SIM = "demo_simulated"
EVID_SYNCED = "offline_synced"

FEEDBACK_TP = "true_positive"
FEEDBACK_FP = "false_positive"
FEEDBACK_INCONCLUSIVE = "inconclusive"
