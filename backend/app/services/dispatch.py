"""Dispatch: nearest eligible inspectors + cryptographically auditable assignment."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.geofence import haversine_m
from app.core.randomization import assignment_commitment, hybrid_priority, random_hex
from app.models.common import INSP_ASSIGNED
from app.models.ops import (
    AssignmentEvent, DispatchRecord, Inspection, InspectionLocation, OutdoorEvent,
)
from app.models.registry import Project
from app.models.users import User
from app.services.codes import gen_inspection_code

MAX_OPEN_PER_INSPECTOR = 3
DEFAULT_RADIUS_M = 25_000  # 25 km neighbourhood for dispatch (demo configurable)

_OPEN_STATUSES = ("assigned", "activated", "in_progress")


def _inspector_position(db: Session, inspector_id: int) -> tuple[float | None, float | None]:
    latest = (db.query(InspectionLocation)
              .join(Inspection, InspectionLocation.inspection_id == Inspection.id)
              .filter(Inspection.assigned_inspector_id == inspector_id)
              .order_by(InspectionLocation.ts.desc()).first())
    if latest:
        return latest.lat, latest.lng
    u = db.get(User, inspector_id)
    return (u.lat, u.lng) if u else (None, None)


def eligible_inspectors(db: Session, project: Project) -> list[dict]:
    inspectors = db.query(User).filter(User.role == "pmu", User.is_active.is_(True)).all()
    out: list[dict] = []
    for u in inspectors:
        open_count = db.query(Inspection).filter(
            Inspection.assigned_inspector_id == u.id,
            Inspection.status.in_(_OPEN_STATUSES),
        ).count()
        if open_count >= MAX_OPEN_PER_INSPECTOR:
            continue
        lat, lng = _inspector_position(db, u.id)
        distance_m = (haversine_m(lat, lng, project.lat, project.lng)
                      if lat is not None and lng is not None else None)
        out.append({
            "inspector": u,
            "distance_m": distance_m,
            "open_count": open_count,
            "inside_radius": distance_m is None or distance_m <= DEFAULT_RADIUS_M,
        })
    return out


def pick_and_assign(
    db: Session,
    *,
    project: Project,
    actor: User,
    kind: str,
    risk_signal: float = 0.0,
    reason: str = "",
    trigger_alert_id: int | None = None,
    outdoor_event: OutdoorEvent | None = None,
    inspector: User | None = None,
) -> tuple[Inspection, AssignmentEvent, DispatchRecord]:
    """Select an inspector (hybrid random + proximity) and open a blind assignment."""
    pool = eligible_inspectors(db, project)
    if not pool:
        raise ValueError("No eligible inspectors available (workload cap or none in radius)")

    if inspector is not None:
        chosen = next((c for c in pool if c["inspector"].id == inspector.id), None)
        if chosen is None:
            raise ValueError("Requested inspector is not eligible right now")
        method = "direct"
        rationale_bits = ["direct nomination by dispatching officer"]
    else:
        nearby = [c for c in pool if c["inside_radius"]] or pool
        for cand in nearby:
            cand["draw"] = hybrid_priority(risk_signal, risk_weight=0.55)
        best = min(nearby, key=lambda c: (c["draw"], c["distance_m"] if c["distance_m"] is not None else float("inf")))
        chosen = best
        method = "risk_hybrid"
        dist_note = (f"{best['distance_m']:.0f} m away"
                     if best["distance_m"] is not None else "distance unknown")
        rationale_bits = [
            f"randomised draw {best['draw']:.3f} over {len(nearby)} eligible inspectors "
            f"({dist_note}); hybrid of uniform randomness and validated risk "
            f"(signal {risk_signal:.2f}) preserves unpredictability",
        ]

    nonce = random_hex(16)
    code = gen_inspection_code(kind)
    now = datetime.now(timezone.utc)
    commitment = assignment_commitment(nonce, code, now.isoformat())

    inspection = Inspection(
        code=code,
        project_id=project.id,
        assigned_inspector_id=chosen["inspector"].id,
        assignment_kind=kind,
        trigger_alert_id=trigger_alert_id,
        outdoor_event_id=outdoor_event.id if outdoor_event else None,
        status=INSP_ASSIGNED,
        reason=reason or None,
        blind_until_activation=True,
        activation_nonce=nonce,
        commitment_hash=commitment,
        lat=project.lat,
        lng=project.lng,
        geofence_radius_m=project.geofence_radius_m,
        risk_signal_before=risk_signal,
    )
    db.add(inspection)
    db.flush()

    assignment_event = AssignmentEvent(
        inspection_id=inspection.id,
        actor_id=actor.id,
        method=method,
        ts=now,
        nonce=nonce,
        commitment=commitment,
        pool_size=len(pool),
        risk_signal=risk_signal,
        random_priority=round(chosen.get("draw", 0.0), 4),
        final_priority=round(chosen.get("draw", 0.0), 4),
        candidate_ids=[c["inspector"].id for c in pool],
        detail={"inspector_id": chosen["inspector"].id,
                "distance_m": chosen["distance_m"]},
    )
    db.add(assignment_event)

    dispatch = DispatchRecord(
        inspection_id=inspection.id,
        actor_id=actor.id,
        criteria={"radius_m": DEFAULT_RADIUS_M, "method": method,
                  "workload_cap": MAX_OPEN_PER_INSPECTOR, "risk_signal": risk_signal},
        candidates=[c["inspector"].id for c in pool],
        rationale=" | ".join(rationale_bits),
    )
    db.add(dispatch)

    audit(db, actor_id=actor.id, actor_role=actor.role, action="inspection_assigned",
          object_type="inspection", object_id=inspection.code,
          detail={"method": method, "nonce": nonce, "commitment": commitment,
                  "inspector_id": chosen["inspector"].id,
                  "project_code": project.code, "kind": kind}, commit=False)
    db.commit()
    return inspection, assignment_event, dispatch


def random_spot_check(
    db: Session, *, project: Project, actor: User,
    outdoor_event: OutdoorEvent | None = None,
    trigger_alert_id: int | None = None, reason: str = "",
) -> tuple[Inspection, AssignmentEvent, DispatchRecord]:
    """Random spot-check dispatch (event-day, surge follow-up, QR anomaly)."""
    return pick_and_assign(
        db, project=project, actor=actor, kind="spot_check",
        reason=reason or "Random spot-check", trigger_alert_id=trigger_alert_id,
        outdoor_event=outdoor_event,
    )
