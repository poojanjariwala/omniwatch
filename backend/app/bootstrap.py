"""Idempotent SAMPLE/DEMO data bootstrap.

Never run against production: every entity carries a DEMO-* prefix and the UI
shows a persistent "DEMO MODE" banner. Used by the seed script and by the
compose `api` service when OMNIWATCH_SEED_ON_START=true.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.common import EVT_REGISTERED
from app.models.cv import Camera
from app.models.ops import Distribution, OutdoorEvent, Project, QrCode
from app.models.users import Organization, User
from app.services.cv.engine import ingest_project_cameras
from app.services.qr import issue_batch
from app.config import settings
from app.core import supabase as sb
from app.core.security import hash_password

# Delhi-area demo coordinates (clearly sample sites).
_DELHI = {"lat": 28.6139, "lng": 77.2090}

SEED_USERS = [
    {"email": "admin@omniwatch.demo.in", "password": "Admin@Demo123",
     "full_name": "A. Sharma", "role": "dosje", "state_code": "DL"},
    {"email": "state@omniwatch.demo.in", "password": "State@Demo123",
     "full_name": "S. Iyer", "role": "state", "state_code": "DL"},
    {"email": "ngo@demo.org", "password": "Ngo@Demo123",
     "full_name": "N. Gupta", "role": "ngo", "state_code": "DL"},
    {"email": "ngo2@demo.org", "password": "Ngo2@Demo123",
     "full_name": "P. Kaur", "role": "ngo", "state_code": "DL"},
    {"email": "rakesh@pmu.demo.in", "password": "Pmu@Demo123",
     "full_name": "Rakesh Kumar", "role": "pmu", "state_code": "DL"},
    {"email": "meena@pmu.demo.in", "password": "Pmu@Demo123",
     "full_name": "Meena Devi", "role": "pmu", "state_code": "DL"},
    {"email": "ben@demo.in", "password": "Ben@Demo123",
     "full_name": "Beneficiary Demo", "role": "beneficiary", "state_code": "DL"},
]

SEED_ORGS = [
    {"name": "Demo Vikas Seva Kendra", "kind": "ngo", "state_code": "DL",
     "reg_number": "DEMO-REG-001", "district": "Central Delhi"},
    {"name": "Demo Shiksha Samiti", "kind": "ngo", "state_code": "DL",
     "reg_number": "DEMO-REG-002", "district": "South Delhi"},
    {"name": "Demo Urban Livelihood Mission Cell", "kind": "gov", "state_code": "DL",
     "reg_number": "DEMO-GOV-001", "district": "New Delhi"},
]


def _utc(days: float = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def ensure_seed_data(db: Session | None = None) -> None:
    own = db is None
    session = db or SessionLocal()
    try:
        _seed(session)
    finally:
        if own:
            session.close()


def _provision_supabase_users(db: Session, users: dict[str, User]) -> None:
    """Create demo accounts in Supabase Auth and link supabase_uid (best effort)."""
    if not (settings.supabase_enabled and settings.supabase_service_key):
        return
    for spec in SEED_USERS:
        user = users.get(spec["email"])
        if user is None or user.supabase_uid:
            continue
        try:
            created = sb.admin_create_user(spec["email"], spec["password"],
                                           spec["full_name"])
            uid = created.get("id")
            if uid:
                user.supabase_uid = uid
        except sb.SupabaseError as exc:
            # Duplicate or auth not configured — mapping by email still works.
            print(f"  supabase provisioning skipped for {spec['email']}: {exc}")  # noqa: T201
    db.commit()


def _seed(db: Session) -> None:
    orgs: dict[str, Organization] = {}
    for spec in SEED_ORGS:
        org = db.query(Organization).filter(Organization.reg_number == spec["reg_number"]).first()
        if org is None:
            org = Organization(**spec)
            db.add(org)
            db.flush()
        orgs[spec["reg_number"]] = org

    users: dict[str, User] = {}
    for spec in SEED_USERS:
        user = db.query(User).filter(User.email == spec["email"]).first()
        if user is None:
            role = spec["role"]
            org_id = None
            if role == "ngo":
                org_id = orgs["DEMO-REG-001" if spec["email"] == "ngo@demo.org"
                            else "DEMO-REG-002"].id
            user = User(
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                full_name=spec["full_name"],
                role=role,
                state_code=spec["state_code"],
                org_id=org_id,
            )
            db.add(user)
            db.flush()
        users[spec["email"]] = user

    # Position two inspectors: Rakesh near the demo centre, Meena far away.
    rakesh = users["rakesh@pmu.demo.in"]
    if rakesh.lat is None:
        rakesh.lat = _DELHI["lat"] - 0.01
        rakesh.lng = _DELHI["lng"] + 0.02
        rakesh.last_position_at = _utc()
    meena = users["meena@pmu.demo.in"]
    if meena.lat is None:
        meena.lat = 19.0760  # ~1,100 km away (Mumbai) — makes dispatch distance visible
        meena.lng = 72.8777
        meena.last_position_at = _utc()

    projects: dict[str, Project] = {}
    project_specs = [
        {"code": "DEMO-CENTRE-01", "name": "Demo Nutrition Support Centre 12",
         "scheme": "Supplementary Nutrition (sample)", "category": "centre",
         "org": "DEMO-REG-001", "reported": 120, "hours": "09:00-17:00",
         "lat": _DELHI["lat"], "lng": _DELHI["lng"]},
        {"code": "DEMO-DIST-01", "name": "Demo Ration Distribution Point 3",
         "scheme": "In-kind distribution (sample)", "category": "distribution",
         "org": "DEMO-REG-002", "reported": 200, "hours": "08:00-16:00",
         "lat": _DELHI["lat"] + 0.035, "lng": _DELHI["lng"] - 0.015},
        {"code": "DEMO-OUTDOOR-01", "name": "Demo Remote Village Camp Hub",
         "scheme": "Outreach distribution (sample)", "category": "outdoor",
         "org": "DEMO-REG-001", "reported": 90, "hours": "event-day",
         "lat": _DELHI["lat"] + 0.12, "lng": _DELHI["lng"] + 0.08},
    ]
    for spec in project_specs:
        project = db.query(Project).filter(Project.code == spec["code"]).first()
        if project is None:
            project = Project(
                code=spec["code"], name=spec["name"], scheme=spec["scheme"],
                category=spec["category"], org_id=orgs[spec["org"]].id,
                description="SAMPLE/DEMO project — not a real scheme or site.",
                address=f"{spec['name']} (demo address)", lat=spec["lat"],
                lng=spec["lng"], reported_beneficiaries=spec["reported"],
                operational_hours=spec["hours"],
            )
            db.add(project)
            db.flush()
        projects[spec["code"]] = project

    _provision_supabase_users(db, users)

    # Simulator cameras on each project (deterministic, scriptable).
    for code, project in projects.items():
        cam = db.query(Camera).filter(Camera.project_id == project.id).first()
        if cam is None:
            cam = Camera(
                project_id=project.id,
                name=f"{code} camera A (simulator)",
                source_type="simulator",
                ingest_every_seconds=30,
                enabled=True,
            )
            db.add(cam)
            db.flush()

    db.commit()

    # Warm adaptive baselines with healthy history (each warm cycle is one
    # simulated window; MIN_SAMPLES=4, we run 6 per project so the first demo
    # surge is comparable against an established baseline).
    for project in projects.values():
        for _ in range(6):
            ingest_project_cameras(db, project_id=project.id)

    # Demo distribution batches + QR codes for scenario B.
    dist_project = projects["DEMO-DIST-01"]
    if db.query(Distribution).filter(Distribution.project_id == dist_project.id).count() == 0:
        issue_batch(db, project=dist_project, org_id=dist_project.org_id,
                    actor=users["ngo2@demo.org"],
                    title="SAMPLE ration handout batch (12 items)", count=12)
    centre_project = projects["DEMO-CENTRE-01"]
    if db.query(Distribution).filter(Distribution.project_id == centre_project.id).count() == 0:
        issue_batch(db, project=centre_project, org_id=centre_project.org_id,
                    actor=users["ngo@demo.org"],
                    title="SAMPLE nutrition handout batch (20 items)", count=20)

    # Outdoor event scheduled > 48 h ahead (registered, awaiting approval).
    outdoor = projects["DEMO-OUTDOOR-01"]
    ev = db.query(OutdoorEvent).filter(OutdoorEvent.project_id == outdoor.id).first()
    if ev is None:
        ev = OutdoorEvent(
            code="OWE-DEMO-OUTDOOR", org_id=outdoor.org_id, project_id=outdoor.id,
            title="SAMPLE village distribution camp (72 h ahead)",
            description="Demonstration outdoor event for scenario C.",
            address="Demo village street corner (sample)",
            lat=outdoor.lat + 0.002, lng=outdoor.lng - 0.001,
            scheduled_at=_utc(days=3),
            status=EVT_REGISTERED,
            created_by=users["ngo@demo.org"].id,
        )
        db.add(ev)
    db.commit()
