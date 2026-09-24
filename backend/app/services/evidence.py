"""Evidence capture pipeline.

Rules enforced server-side:
  * gallery/file uploads are NOT accepted as inspection evidence — the caller
    must declare a live camera source (or an explicit demo-simulated source);
  * coordinates are validated against the inspection's geofence;
  * filenames are always server-generated (SHA-256 of the bytes);
  * every artifact is hashed and linked into the case chain-of-custody.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import audit
from app.core.evidence_chain import CHAIN_GENESIS, chain_hash, sha256_file
from app.core.geofence import within_geofence
from app.core.timeutil import as_utc, utc_naive_iso
from app.models.common import EVID_DEMO_SIM, EVID_LIVE, EVID_SYNCED, utcnow
from app.models.ops import Alert, Case, Evidence, Inspection, Project
from app.models.users import User

# Government reviewer attachments (no camera claim) — used on case files.
EVID_OFFICIAL = "official_review"

PHOTO_LIMIT_BYTES = settings.max_photo_mb * 1024 * 1024
VIDEO_LIMIT_BYTES = settings.max_video_mb * 1024 * 1024
DEMO_SOURCES = {EVID_DEMO_SIM}


def sniff_mime(data: bytes, declared: str | None) -> tuple[str, str] | None:
    """Return (mime, extension) when the bytes match the content allowlist.

    Content decides, not the declared Content-Type. Checks are strict:
    JPEG/PNG signatures, a real RIFF/WEBP pair, an MP4/MOV `ftyp` box (a bare
    0x000000 prefix alone would accept arbitrary files) and a %PDF header for
    official reviewer attachments.
    """
    del declared  # content-based detection only
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        if data[8:12] == b"qt  ":
            return "video/quicktime", ".mov"
        return "video/mp4", ".mp4"
    if data.startswith(b"%PDF"):  # official reviewer attachments only
        return "application/pdf", ".pdf"
    return None


def _base_dir() -> Path:
    d = Path(settings.upload_dir).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _latest_prev_hash(db: Session, *, inspection_id: int | None,
                      case_id: int | None) -> str:
    if inspection_id:
        last = (db.query(Evidence)
                .filter(Evidence.inspection_id == inspection_id)
                .order_by(Evidence.id.desc()).first())
    elif case_id:
        last = (db.query(Evidence)
                .filter(Evidence.case_id == case_id)
                .order_by(Evidence.id.desc()).first())
    else:
        last = None
    return last.chain_hash if last else CHAIN_GENESIS


def _geofence_centre(db: Session, *, inspection: Inspection | None,
                     case: Case | None) -> Project | None:
    project = None
    if inspection is not None:
        project = db.get(Project, inspection.project_id)
    elif case is not None and case.project_id:
        project = db.get(Project, case.project_id)
    return project


def store_evidence(
    db: Session,
    *,
    actor: User,
    data: bytes,
    declared_mime: str,
    kind: str,
    captured_at: datetime | None,
    lat: float | None,
    lng: float | None,
    source: str,
    inspection: Inspection | None = None,
    case: Case | None = None,
    alert: Alert | None = None,
    client_ref: str | None = None,
) -> Evidence:
    """Validate, persist and chain a captured artifact."""
    # 1. Idempotency for the offline queue (retries reuse the server artifact).
    if client_ref and inspection:
        existing = (db.query(Evidence)
                    .filter(Evidence.client_ref == client_ref,
                            Evidence.inspection_id == inspection.id).first())
        if existing:
            return existing

    # 2. Live-camera rule (photos must come from the in-app camera pipeline).
    if source not in (EVID_LIVE, EVID_DEMO_SIM, EVID_SYNCED, EVID_OFFICIAL):
        raise ValueError("Evidence source not permitted (gallery uploads are blocked "
                         "for inspection evidence)")
    if source == EVID_LIVE and (lat is None or lng is None):
        # A live capture without coordinates cannot be geo-bound.
        raise ValueError("Live evidence requires capture coordinates")

    # 3. Size + content checks.
    if len(data) == 0:
        raise ValueError("Empty file rejected")
    limit = VIDEO_LIMIT_BYTES if kind == "video" else PHOTO_LIMIT_BYTES
    if len(data) > limit:
        raise ValueError(f"File exceeds allowed size ({limit // (1024 * 1024)} MB)")
    sniffed = sniff_mime(data, declared_mime)
    if sniffed is None:
        raise ValueError("File type not allowed")

    # 4. Geo-binding against the geofence (server-side, 50 m reference).
    project = _geofence_centre(db, inspection=inspection, case=case)
    geofence_ok: bool | None = None
    distance_m: float | None = None
    if project is not None and lat is not None and lng is not None:
        radius = (inspection.geofence_radius_m if inspection
                  else project.geofence_radius_m or settings.default_geofence_radius_m)
        geofence_ok, distance_m = within_geofence(lat, lng, project.lat, project.lng, radius)
    elif inspection is not None and source == EVID_LIVE:
        raise ValueError("Evidence has no coordinates; cannot verify geofence")

    # 5. Persist bytes under a server-generated name (never the client filename).
    mime, ext = sniffed
    sha = _sha256(data)
    day = utcnow()
    rel_dir = Path(str(day.year)) / f"{day.month:02d}"
    target = _base_dir() / rel_dir
    target.mkdir(parents=True, exist_ok=True)
    stored = target / f"{sha}{ext}"
    if not stored.exists():
        stored.write_bytes(data)

    meta = {
        "captured_at": utc_naive_iso(as_utc(captured_at) or utcnow()),
        "kind": kind,
        "inspection_id": inspection.id if inspection else None,
        "case_id": case.id if case else None,
        "alert_id": alert.id if alert else None,
        "project_id": project.id if project else None,
        "source": source,
        "lat": lat, "lng": lng,
        "client_ref": client_ref,
        "geofence_ok": geofence_ok,
        "distance_m": round(distance_m, 1) if distance_m is not None else None,
        "captured_by": actor.id, "mime": mime,
    }
    prev = _latest_prev_hash(db, inspection_id=inspection.id if inspection else None,
                             case_id=case.id if case else None)
    chain = chain_hash(prev, sha, meta)

    evidence = Evidence(
        kind=kind, inspection_id=inspection.id if inspection else None,
        case_id=case.id if case else None, alert_id=alert.id if alert else None,
        project_id=project.id if project else None,
        mime=mime, size_bytes=len(data), sha256=sha,
        chain_prev_hash=prev, chain_hash=chain,
        stored_name=stored.relative_to(_base_dir()).as_posix(),
        source=source, client_ref=client_ref,
        captured_at=captured_at or utcnow(), lat=lat, lng=lng,
        geofence_ok=geofence_ok,
        distance_m=round(distance_m, 1) if distance_m is not None else None,
        artifact_meta=meta,
    )
    db.add(evidence)
    db.flush()
    audit(db, actor_id=actor.id, actor_role=actor.role, action="evidence_added",
          object_type="evidence", object_id=evidence.id,
          detail={"kind": kind, "sha256": sha[:16], "source": source,
                  "geofence_ok": geofence_ok,
                  "inspection": inspection.code if inspection else None}, commit=False)
    return evidence


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def resolve_storage_path(db: Session, evidence: Evidence) -> Path:
    return _base_dir() / evidence.stored_name


def verify_artifact(db: Session, evidence: Evidence) -> dict:
    """Recompute and compare stored hashes (integrity check)."""
    path = resolve_storage_path(db, evidence)
    if not path.exists():
        return {"ok": False, "reason": "file_missing"}
    actual_sha = sha256_file(path)
    meta = dict(evidence.artifact_meta or {})
    meta.update({
        "captured_at": utc_naive_iso(as_utc(evidence.captured_at)),
        "inspection_id": evidence.inspection_id,
        "case_id": evidence.case_id,
        "alert_id": evidence.alert_id,
        "project_id": evidence.project_id,
        "client_ref": evidence.client_ref,
    })
    expected_chain = chain_hash(evidence.chain_prev_hash, actual_sha, meta)
    return {
        "ok": actual_sha == evidence.sha256 and expected_chain == evidence.chain_hash,
        "sha256_match": actual_sha == evidence.sha256,
        "chain_match": expected_chain == evidence.chain_hash,
    }
