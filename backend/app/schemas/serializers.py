"""Role-scoped serializers.

Field-level blindness is enforced here: NGO responses never carry risk scores,
internal alerts or any schedule/intelligence field; government responses always
explain every alert.
"""
from __future__ import annotations

from datetime import datetime

from app.models.cv import Camera, CctvEvent
from app.models.ops import (
    Alert, Case, Distribution, Evidence, Inspection, InspectionLocation,
    OutdoorEvent, QrCode, QrScanLog,
)
from app.models.registry import Project
from app.models.users import User


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# --- Users -------------------------------------------------------------------

def public_user(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
        "phone": u.phone, "state_code": u.state_code, "org_id": u.org_id,
    }


# --- Projects (NGO responses strip risk) -------------------------------------

def project_public(p: Project, *, for_role: str, org_name: str | None = None,
                   camera_count: int = 0, open_alerts: int = 0) -> dict:
    out = {
        "id": p.id, "code": p.code, "name": p.name, "scheme": p.scheme,
        "category": p.category, "description": p.description, "address": p.address,
        "lat": p.lat, "lng": p.lng, "geofence_radius_m": p.geofence_radius_m,
        "status": p.status, "reported_beneficiaries": p.reported_beneficiaries,
        "org_id": p.org_id, "org_name": org_name,
        "camera_count": camera_count, "open_alerts": open_alerts,
    }
    if for_role != "ngo":  # NGO never sees risk or alert-level intelligence
        out["risk_score"] = p.risk_score
        out["risk_status"] = p.risk_status
        out["risk_reason"] = p.risk_reason
        out["risk_last_update"] = _iso(p.risk_last_update)
    return out


# --- Alerts ------------------------------------------------------------------

def alert_public(a: Alert, project_name: str | None = None) -> dict:
    return {
        "id": a.id, "code": a.code, "kind": a.kind, "severity": a.severity,
        "title": a.title, "summary": a.summary,
        "project_id": a.project_id, "project_name": project_name,
        "occurred_at": _iso(a.occurred_at), "location": a.location,
        "signals": a.signals or [], "evidence_refs": a.evidence_refs or [],
        "risk_signal": a.risk_signal,
        "recommended_action": a.recommended_action,
        "ai_generated": a.ai_generated, "status": a.status,
        "resolved_by": a.resolved_by, "resolved_at": _iso(a.resolved_at),
        "feedback": a.feedback, "feedback_note": a.feedback_note,
        "case_id": a.case_id, "inspection_id": a.inspection_id,
    }


# --- Inspections -------------------------------------------------------------

def _route_timeline(locations: list[InspectionLocation]) -> list[dict]:
    return [{
        "ts": _iso(l.ts), "lat": l.lat, "lng": l.lng,
        "within_geofence": l.within_geofence, "distance_m": l.distance_m,
        "device": l.device,
    } for l in locations]


def inspection_blind(i: Inspection, inspector_name: str) -> dict:
    """Blind envelope view: no project intelligence until activation."""
    return {
        "id": i.id, "code": i.code, "status": i.status,
        "assignment_kind": i.assignment_kind, "assigned_inspector_id": i.assigned_inspector_id,
        "inspector_name": inspector_name,
        "assigned_at": _iso(i.created_at), "blind": i.blind_until_activation,
        "reason": i.reason, "geofence_radius_m": i.geofence_radius_m,
    }


def inspection_full(i: Inspection, *, project: Project | None,
                    inspector: User | None, include_evidence: bool = True) -> dict:
    evidences = i.evidence if include_evidence else []
    return {
        "id": i.id, "code": i.code, "status": i.status,
        "assignment_kind": i.assignment_kind,
        "assigned_inspector_id": i.assigned_inspector_id,
        "inspector_name": inspector.full_name if inspector else None,
        "assigned_at": _iso(i.created_at),
        "activated_at": _iso(i.activated_at), "revealed_at": _iso(i.revealed_at),
        "arrival_at": _iso(i.arrival_at), "submitted_at": _iso(i.submitted_at),
        "completed_at": _iso(i.completed_at),
        "blind": i.blind_until_activation,
        "project": project_public(project, for_role="pmu",
                                  org_name=project.org.name if project and project.org else None)
        if project else None,
        "reason": i.reason, "risk_signal_before": i.risk_signal_before,
        "geofence_radius_m": i.geofence_radius_m,
        "checklist": i.checklist or [], "notes": i.notes,
        "result_summary": i.result_summary,
        "verification_passed": i.verification_passed,
        "route_warnings": i.route_warnings or [],
        "decision_notes": i.decision_notes,
        "commitment_hash": i.commitment_hash,
        "evidence": [evidence_public(e) for e in evidences],
        "route_timeline": _route_timeline(i.locations),
    }


# --- Evidence ----------------------------------------------------------------

def evidence_public(e: Evidence) -> dict:
    return {
        "id": e.id, "kind": e.kind, "mime": e.mime, "size_bytes": e.size_bytes,
        "sha256": e.sha256, "chain_prev_hash": e.chain_prev_hash,
        "chain_hash": e.chain_hash, "source": e.source,
        "captured_at": _iso(e.captured_at), "lat": e.lat, "lng": e.lng,
        "geofence_ok": e.geofence_ok, "distance_m": e.distance_m,
        "client_ref": e.client_ref, "metadata": e.artifact_meta,
        "inspection_id": e.inspection_id, "case_id": e.case_id,
        "alert_id": e.alert_id, "project_id": e.project_id,
    }


# --- CCTV --------------------------------------------------------------------

def camera_public(c: Camera, project_name: str | None = None,
                  project_code: str | None = None) -> dict:
    return {
        "id": c.id, "project_id": c.project_id, "project_name": project_name,
        "project_code": project_code, "name": c.name, "source_type": c.source_type,
        "enabled": c.enabled, "ingest_every_seconds": c.ingest_every_seconds,
        "last_ingest_at": _iso(c.last_ingest_at),
        "last_frame_count": c.last_frame_count, "last_error": c.last_error,
    }


def cctv_event_public(e: CctvEvent) -> dict:
    return {
        "id": e.id, "camera_id": e.camera_id, "project_id": e.project_id,
        "ts": _iso(e.ts), "occupancy": e.occupancy, "items_handed": e.items_handed,
        "window_seconds": e.window_seconds, "processed_by": e.processed_by,
    }


# --- QR ----------------------------------------------------------------------

def distribution_public(d: Distribution, *, total: int = 0, consumed: int = 0,
                        project_name: str | None = None,
                        org_name: str | None = None) -> dict:
    return {
        "id": d.id, "code": d.code, "project_id": d.project_id,
        "project_name": project_name, "org_id": d.org_id, "org_name": org_name,
        "title": d.title, "distribution_date": d.distribution_date.isoformat(),
        "total_items": d.total_items, "status": d.status,
        "consumed": consumed, "created_at": _iso(d.created_at),
    }


def qr_code_public(q: QrCode) -> dict:
    return {
        "id": q.id, "code": q.code, "distribution_id": q.distribution_id,
        "project_id": q.project_id, "serial": q.serial, "status": q.status,
        "recipient_token": q.recipient_token,
        "consumed_at": _iso(q.consumed_at),
    }


def scan_log_public(s: QrScanLog, code_code: str | None = None,
                    actor_name: str | None = None) -> dict:
    return {
        "id": s.id, "ok": s.ok, "reason": s.reason, "code": code_code,
        "scanned_by": s.scanned_by, "actor_name": actor_name,
        "lat": s.lat, "lng": s.lng, "created_at": _iso(s.created_at),
        "detail": s.detail,
    }


# --- Outdoor events ----------------------------------------------------------

def outdoor_event_public(e: OutdoorEvent, org_name: str | None = None) -> dict:
    return {
        "id": e.id, "code": e.code, "org_id": e.org_id, "org_name": org_name,
        "project_id": e.project_id, "title": e.title, "description": e.description,
        "address": e.address, "lat": e.lat, "lng": e.lng,
        "scheduled_at": _iso(e.scheduled_at), "registered_at": _iso(e.registered_at),
        "status": e.status, "live_lat": e.live_lat, "live_lng": e.live_lng,
        "last_broadcast_at": _iso(e.last_broadcast_at),
        "spot_inspection_id": e.spot_inspection_id,
    }


# --- Cases & audit -----------------------------------------------------------

def case_public(c: Case, project_name: str | None = None,
                alert_count: int = 0, evidence_count: int = 0,
                inspection_count: int = 0) -> dict:
    return {
        "id": c.id, "code": c.code, "title": c.title, "description": c.description,
        "project_id": c.project_id, "project_name": project_name,
        "status": c.status, "opened_by": c.opened_by, "opened_at": _iso(c.opened_at),
        "closed_by": c.closed_by, "closed_at": _iso(c.closed_at),
        "closure_note": c.closure_note, "closure_action": c.closure_action,
        "alert_count": alert_count, "evidence_count": evidence_count,
        "inspection_count": inspection_count,
    }
