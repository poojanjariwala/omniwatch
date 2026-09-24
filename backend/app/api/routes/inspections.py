"""Inspection lifecycle (FR-06…10 + scenario A).

Blind envelope: an inspector sees only today's own assignments; project
intelligence is released server-side at activation after a device check.
Location, evidence and arrival are correlated for route integrity.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import audit
from app.core.geofence import haversine_m, validate_lat_lng, within_geofence
from app.core.limits import DISPATCH_LIMIT, UPLOAD_LIMIT, limiter
from app.core.timeutil import as_utc, parse_iso_utc
from app.core.rbac import (
    Db, GovernmentUser, PmuUser, SensitiveUser, can_access_project, require_roles,
)
from app.models.common import (
    EVID_LIVE, EVID_DEMO_SIM, EVID_SYNCED, INSP_ACTIVATED, INSP_ASSIGNED, INSP_COMPLETED,
    INSP_IN_PROGRESS, INSP_SUBMITTED, utcnow,
)
from app.models.ops import (
    Alert, DeviceCheck, Evidence, Inspection, InspectionLocation, OutdoorEvent,
    Project,
)
from app.models.users import Organization, User
from app.schemas.serializers import evidence_public, inspection_blind, inspection_full
from app.services import alerts as alert_svc
from app.services.dispatch import pick_and_assign, random_spot_check
from app.services.evidence import VIDEO_LIMIT_BYTES, store_evidence

router = APIRouter(prefix="/api/inspections", tags=["inspections"])

CHECKLIST_TEMPLATES = {
    "centre": [
        {"item": "Beneficiary attendance register is maintained and signed", "id": "register"},
        {"item": "Beneficiaries present match the register/list", "id": "list_match"},
        {"item": "Distribution quantities match the approved plan", "id": "quantities"},
        {"item": "Site operational during stated hours", "id": "hours"},
    ],
    "distribution": [
        {"item": "QR/item scanning is in use at the distribution desk", "id": "qr_scan"},
        {"item": "Items handed out match the register entries", "id": "items_match"},
        {"item": "Beneficiary identity is being verified", "id": "identity"},
    ],
    "outdoor": [
        {"item": "Event site matches the registered GPS pin", "id": "site_pin"},
        {"item": "Crowd and safety measures in place", "id": "safety"},
        {"item": "Beneficiary list available on site", "id": "list"},
    ],
    "skill": [
        {"item": "Training session underway with registered learners", "id": "learners"},
        {"item": "Attendance/outcome records maintained", "id": "records"},
    ],
}


def _project_of(db, inspection: Inspection) -> Project:
    p = db.get(Project, inspection.project_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inspection project missing")
    return p


def _check_inspection_scope(db, inspection_id: int, user) -> Inspection:
    insp = db.get(Inspection, inspection_id)
    if insp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    project = db.get(Project, insp.project_id) if insp.project_id else None
    if user.role == "pmu":
        if insp.assigned_inspector_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    elif not (project and can_access_project(user, project)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Inspection not found")
    return insp


def _own_active_inspection(db, inspection_id: int, user) -> Inspection:
    insp = _check_inspection_scope(db, inspection_id, user)
    if insp.assigned_inspector_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your assignment")
    return insp


# ---------------------------------------------------------------------------
# Government dispatch / listing
# ---------------------------------------------------------------------------

class DispatchIn(BaseModel):
    project_id: int
    kind: str = Field(pattern="^(risk_priority|random_surge|spot_check|scheduled|recheck)$")
    inspector_id: int | None = None
    reason: str = Field(default="", max_length=500)
    risk_signal: float = Field(default=0.0, ge=0.0, le=1.0)


@router.post("/dispatch")
@limiter.limit(DISPATCH_LIMIT)
def dispatch(request: Request, body: DispatchIn, db: Db, user: GovernmentUser):
    """Create a blind inspection. Auditable randomised draw on the server."""
    project = db.get(Project, body.project_id)
    if project is None or not can_access_project(user, project):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    inspector = db.get(User, body.inspector_id) if body.inspector_id else None
    try:
        inspection, event, dispatch_rec = pick_and_assign(
            db, project=project, actor=user, kind=body.kind,
            risk_signal=body.risk_signal, reason=body.reason, inspector=inspector,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    chosen = db.get(User, inspection.assigned_inspector_id)
    return {
        "inspection": inspection_full(inspection, project=project, inspector=chosen),
        "assignment": {
            "method": event.method, "nonce": event.nonce,
            "commitment": event.commitment, "pool_size": event.pool_size,
            "ts": event.ts.isoformat(),
        },
        "dispatch_rationale": dispatch_rec.rationale,
    }


@router.get("")
def list_inspections(db: Db, user: GovernmentUser,
                     status_filter: str | None = None, limit: int = 100):
    q = db.query(Inspection).order_by(Inspection.created_at.desc())
    if status_filter:
        q = q.filter(Inspection.status == status_filter)
    rows = q.limit(min(limit, 500)).all()
    out = []
    for i in rows:
        project = db.get(Project, i.project_id) if i.project_id else None
        if project is not None and not can_access_project(user, project):
            continue
        inspector = db.get(User, i.assigned_inspector_id)
        out.append(inspection_full(i, project=project, inspector=inspector,
                                   include_evidence=False))
    return {"inspections": out}


@router.get("/mine")
def my_assignments(db: Db, user: PmuUser):
    """Inspector view — only today's own assignments, blind until activated."""
    start = utcnow() - timedelta(hours=26)
    rows = (db.query(Inspection)
            .filter(Inspection.assigned_inspector_id == user.id,
                    Inspection.created_at >= start,
                    Inspection.status.in_((INSP_ASSIGNED, INSP_ACTIVATED,
                                           INSP_IN_PROGRESS, INSP_SUBMITTED)))
            .order_by(Inspection.created_at.desc()).all())
    return {"assignments": [inspection_blind(i, user.full_name) for i in rows]}


@router.get("/{inspection_id}")
def get_inspection(inspection_id: int, db: Db,
                   user: Annotated[User, Depends(require_roles("dosje", "state", "pmu"))]):
    insp = _check_inspection_scope(db, inspection_id, user)
    project = _project_of(db, insp)
    inspector = db.get(User, insp.assigned_inspector_id)
    if user.role == "pmu":
        if insp.assigned_inspector_id != user.id:
            # Peers cannot peek at sealed envelopes either.
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        if insp.blind_until_activation:
            # Blind envelope: no project intelligence before activation.
            return inspection_blind(insp, user.full_name)
    return inspection_full(insp, project=project, inspector=inspector)


# ---------------------------------------------------------------------------
# Inspector activation flow
# ---------------------------------------------------------------------------

class LocationIn(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None = Field(default=None, ge=0, le=5000)
    device: dict | None = None


@router.post("/{inspection_id}/device-check")
def device_check(inspection_id: int, db: Db, user: PmuUser):
    """Pre-activation device-integrity signals (simulated in this prototype)."""
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status != INSP_ASSIGNED:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Device check allowed only before activation")
    signals = {
        "attestation": "play_integrity_simulated",
        "integrity_verdict": "pass" if user.demo_device_ok else "fail",
        "mock_location_detected": False,
        "rooted_device": False,
        "generated_at": utcnow().isoformat(),
        "note": "Simulated Play Integrity signals — real attestation is a later phase "
                "(contract retained).",
    }
    verdict = "pass" if user.demo_device_ok else "fail"
    check = DeviceCheck(user_id=user.id, inspection_id=insp.id, signals=signals,
                        verdict=verdict)
    db.add(check)
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="device_check",
          object_type="inspection", object_id=insp.code,
          detail={"verdict": verdict}, commit=False)
    db.commit()
    return {"signals": signals, "verdict": verdict, "check_id": check.id}


@router.post("/{inspection_id}/activate")
def activate(inspection_id: int, db: Db, user: PmuUser):
    """Open the blind envelope: reveals task intelligence only after device check."""
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status != INSP_ASSIGNED:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already activated or closed")
    recent = (db.query(DeviceCheck)
              .filter(DeviceCheck.user_id == user.id,
                      DeviceCheck.inspection_id == insp.id,
                      DeviceCheck.ts >= utcnow() - timedelta(minutes=20))
              .order_by(DeviceCheck.ts.desc()).first())
    if recent is None or recent.verdict != "pass":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail="Device integrity check required before activation")
    insp.blind_until_activation = False
    insp.status = INSP_ACTIVATED
    insp.activated_at = utcnow()
    insp.revealed_at = utcnow()
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="inspection_activated",
          object_type="inspection", object_id=insp.code, commit=False)
    db.commit()

    project = _project_of(db, insp)
    org = db.get(Organization, project.org_id) if project.org_id else None
    return {
        "inspection_id": insp.id, "code": insp.code,
        "commitment_hash": insp.commitment_hash,
        "reason": insp.reason, "kind": insp.assignment_kind,
        "project": {
            "code": project.code, "name": project.name, "scheme": project.scheme,
            "category": project.category, "address": project.address,
            "org_name": org.name if org else None,
            "lat": project.lat, "lng": project.lng,
            "geofence_radius_m": project.geofence_radius_m,
        },
        "checklist": CHECKLIST_TEMPLATES.get(project.category, []),
    }


@router.post("/{inspection_id}/start")
def start(inspection_id: int, db: Db, user: PmuUser):
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status != INSP_ACTIVATED:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Activate the assignment before starting")
    insp.status = INSP_IN_PROGRESS
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="inspection_started",
          object_type="inspection", object_id=insp.code, commit=False)
    db.commit()
    return {"status": insp.status}


@router.post("/{inspection_id}/location")
def report_location(inspection_id: int, body: LocationIn, db: Db, user: PmuUser):
    """GPS heartbeat — validated server-side against the geofence."""
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status not in (INSP_ACTIVATED, INSP_IN_PROGRESS):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Location reporting allowed during the visit")
    if not validate_lat_lng(body.lat, body.lng):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Invalid coordinates")
    within, dist = within_geofence(body.lat, body.lng, insp.lat, insp.lng,
                                   insp.geofence_radius_m)
    loc = InspectionLocation(
        inspection_id=insp.id, ts=utcnow(), lat=body.lat, lng=body.lng,
        within_geofence=within, distance_m=round(dist, 1), device=body.device,
    )
    db.add(loc)
    user.lat, user.lng, user.last_position_at = body.lat, body.lng, utcnow()
    if within and insp.arrival_at is None:
        insp.arrival_at = utcnow()
        audit(db, actor_id=user.id, actor_role=user.role, action="inspector_arrived",
              object_type="inspection", object_id=insp.code,
              detail={"distance_m": round(dist, 1)}, commit=False)
    db.commit()
    return {"within_geofence": within, "distance_m": round(dist, 1),
            "arrival_recorded": insp.arrival_at is not None}


class ChecklistIn(BaseModel):
    answers: list[dict] = Field(default_factory=list)


@router.post("/{inspection_id}/checklist")
def save_checklist(inspection_id: int, body: ChecklistIn, db: Db, user: PmuUser):
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status not in (INSP_ACTIVATED, INSP_IN_PROGRESS):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Checklist not allowed now")
    sanitized = [{
        "id": str(a.get("id", ""))[:80],
        "passed": bool(a.get("passed")),
        "note": str(a.get("note", ""))[:500],
    } for a in body.answers if isinstance(a, dict)]
    insp.checklist = sanitized
    db.commit()
    return {"saved": len(sanitized)}


class SubmitIn(BaseModel):
    notes: str = Field(default="", max_length=3000)


def _route_integrity(db, insp: Inspection) -> list[str]:
    warnings: list[str] = []
    if insp.arrival_at is None:
        warnings.append("No on-site arrival was recorded inside the geofence")
    evidence = (db.query(Evidence)
                .filter(Evidence.inspection_id == insp.id).order_by(Evidence.id).all())
    geo_fail = [e for e in evidence if e.geofence_ok is False]
    if geo_fail:
        warnings.append(f"{len(geo_fail)} evidence item(s) captured outside the geofence")
    for e in evidence:
        captured = as_utc(e.captured_at)
        activated = as_utc(insp.activated_at)
        if activated and captured and captured < activated - timedelta(minutes=2):
            warnings.append(f"Evidence {e.id} timestamp predates activation")
    submitted = as_utc(insp.submitted_at)
    activated = as_utc(insp.activated_at)
    if activated and submitted and submitted < activated:
        warnings.append("Submission timestamp precedes activation")
    if not insp.checklist:
        warnings.append("Checklist was not completed")
    return warnings


@router.post("/{inspection_id}/submit")
def submit(inspection_id: int, body: SubmitIn, db: Db, user: PmuUser):
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status != INSP_IN_PROGRESS:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Start the visit before submitting")
    insp.status = INSP_SUBMITTED
    insp.submitted_at = utcnow()
    insp.notes = body.notes
    evidence_count = db.query(Evidence).filter(Evidence.inspection_id == insp.id).count()
    insp.result_summary = {
        "evidence_count": evidence_count,
        "evidence_geo_ok": db.query(Evidence).filter(
            Evidence.inspection_id == insp.id, Evidence.geofence_ok.is_(True)).count(),
        "checklist_items": len(insp.checklist or []),
        "route_warnings": _route_integrity(db, insp),
    }
    insp.route_warnings = _route_integrity(db, insp)
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="inspection_submitted",
          object_type="inspection", object_id=insp.code,
          detail={"warnings": insp.route_warnings}, commit=False)
    db.commit()
    return {"status": insp.status, "route_warnings": insp.route_warnings,
            "result_summary": insp.result_summary}


class CompleteIn(BaseModel):
    verification_passed: bool
    decision_notes: str = Field(default="", max_length=2000)


@router.post("/{inspection_id}/complete")
def complete(inspection_id: int, body: CompleteIn, db: Db, user: SensitiveUser):
    """Human decision after evidence review (re-authentication required)."""
    if user.role not in ("dosje", "state", "pmu"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not permitted")
    insp = _check_inspection_scope(db, inspection_id, user)
    if insp.status != INSP_SUBMITTED:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Only submitted inspections can be completed")
    insp.status = INSP_COMPLETED
    insp.completed_at = utcnow()
    insp.verification_passed = body.verification_passed
    insp.decision_notes = body.decision_notes
    db.flush()
    audit(db, actor_id=user.id, actor_role=user.role, action="inspection_completed",
          object_type="inspection", object_id=insp.code,
          detail={"verification_passed": body.verification_passed}, commit=False)

    if insp.trigger_alert_id:
        alert = db.get(Alert, insp.trigger_alert_id)
        if alert and alert.status != "closed":
            note = ("Field inspection verified the concern." if body.verification_passed
                    else "Field inspection did not corroborate the signal.")
            try:
                alert_svc.transition_alert(db, alert, "action_taken",
                                           actor_id=user.id, note=note)
            except ValueError:
                pass
            if body.verification_passed:
                alert.feedback = "true_positive"
            else:
                alert.feedback = "false_positive"
            alert.feedback_note = f"Decision by inspection {insp.code}: {note}"
            alert_svc.update_project_risk(db, _project_of(db, insp))
    db.commit()
    return {"status": insp.status, "verification_passed": body.verification_passed}


# ---------------------------------------------------------------------------
# Evidence capture (geo/time-bound, in-app live camera)
# ---------------------------------------------------------------------------

@router.post("/{inspection_id}/evidence")
@limiter.limit(UPLOAD_LIMIT)
def upload_evidence(request: Request, inspection_id: int, db: Db, user: PmuUser,
                    file: UploadFile,
                    kind: str = Form("photo"),
                    captured_at: str | None = Form(None),
                    lat: float | None = Form(None),
                    lng: float | None = Form(None),
                    source: str = Form(EVID_LIVE),
                    client_ref: str | None = Form(None)):
    """Geo/time-bound evidence. Gallery/file uploads are rejected server-side."""
    insp = _own_active_inspection(db, inspection_id, user)
    if insp.status not in (INSP_ACTIVATED, INSP_IN_PROGRESS):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail="Evidence capture allowed only during the visit")
    if source not in (EVID_LIVE, EVID_DEMO_SIM, EVID_SYNCED):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Gallery uploads are blocked for inspection evidence")
    if source == EVID_SYNCED and not client_ref:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Offline-synced evidence requires its queue client_ref")
    if kind not in ("photo", "video"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Evidence kind must be photo or video")

    captured = None
    if captured_at:
        try:
            captured = parse_iso_utc(captured_at)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="captured_at must be an ISO-8601 timestamp") from exc

    data = file.file.read(VIDEO_LIMIT_BYTES + 1)
    if len(data) > VIDEO_LIMIT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="File exceeds the permitted size")
    try:
        evidence = store_evidence(
            db,
            actor=user,
            data=data,
            declared_mime=file.content_type or "application/octet-stream",
            kind=kind,
            captured_at=captured,
            lat=lat, lng=lng, source=source,
            inspection=insp,
            client_ref=client_ref,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    return evidence_public(evidence)
