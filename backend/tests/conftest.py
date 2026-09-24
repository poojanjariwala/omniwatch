"""Pytest fixtures. Env must be set before app modules are imported."""
from __future__ import annotations

import os
from pathlib import Path

_TEST_DATA = Path(__file__).resolve().parent.parent / "data"
_TEST_DATA.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATA / 'test_omniwatch.db'}"
os.environ["UPLOAD_DIR"] = str(_TEST_DATA / "test_uploads")
os.environ["CV_MODE"] = "sim"
os.environ["DEMO_MODE"] = "true"
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-0123456789"
os.environ["JWT_ACCESS_TTL_MINUTES"] = "60"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["SEED_ON_START"] = "false"
# Raise per-IP route limits so the shared test client isn't throttled.
os.environ["RATE_LOGIN"] = "10000/minute"
os.environ["RATE_REFRESH"] = "10000/minute"
os.environ["RATE_ACTION"] = "10000/minute"
os.environ["RATE_UPLOAD"] = "10000/minute"
os.environ["RATE_QR_SCAN"] = "10000/minute"
os.environ["RATE_DISPATCH"] = "10000/minute"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402


def _reset_schema():
    # SQLite: disable FK enforcement so cyclic tables (alerts<->inspections) can
    # be dropped without ALTER support; recreate immediately after.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest.fixture(scope="session", autouse=True)
def _schema():
    _reset_schema()
    yield


@pytest.fixture(autouse=True)
def clean_db(_schema):
    yield
    _reset_schema()


def _mkuser(db, email: str, role: str, password: str = "Passw0rd!x", org_id=None,
            state_code=None, demo_device_ok: bool = True):
    from app.models.users import User
    u = User(email=email, password_hash=hash_password(password), full_name=email,
             role=role, org_id=org_id, state_code=state_code,
             demo_device_ok=demo_device_ok)
    db.add(u)
    db.commit()
    return u


@pytest.fixture(scope="session")
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(db):
    """Organisations + projects + inspector positions used by most tests."""
    from app.models.registry import Project
    from app.models.users import Organization
    ngo = Organization(name="Test NGO One", kind="ngo", reg_number="T-1",
                       state_code="DL")
    ngo2 = Organization(name="Test NGO Two", kind="ngo", reg_number="T-2",
                        state_code="DL")
    gov = Organization(name="Test PMU Cell", kind="gov", reg_number="T-G",
                       state_code="DL")
    db.add_all([ngo, ngo2, gov])
    db.commit()
    p1 = Project(code="TEST-CENTRE", name="Test Centre", scheme="Nutrition (sample)",
                 category="centre", org_id=ngo.id, lat=28.6139, lng=77.2090,
                 reported_beneficiaries=120)
    p2 = Project(code="TEST-DIST", name="Test Distribution", scheme="Ration (sample)",
                 category="distribution", org_id=ngo2.id, lat=28.65, lng=77.19,
                 reported_beneficiaries=200)
    db.add_all([p1, p2])
    db.commit()
    rakesh = _mkuser(db, "rakesh@test.in", "pmu", org_id=gov.id)
    rakesh.lat, rakesh.lng = p1.lat - 0.01, p1.lng + 0.01
    db.commit()
    return {"ngo": ngo, "ngo2": ngo2, "gov": gov, "p1": p1, "p2": p2,
            "rakesh": rakesh}


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def users(db, seeded):
    from app.models.users import User
    dosje = _mkuser(db, "dosje@test.in", "dosje", state_code="DL")
    state = _mkuser(db, "state@test.in", "state", state_code="DL")
    pmu = seeded["rakesh"]
    meena = _mkuser(db, "meena@test.in", "pmu", org_id=seeded["gov"].id, state_code="DL")
    # ~220 km away so dispatch deterministically prefers Rakesh (nearby).
    meena.lat, meena.lng = seeded["p1"].lat - 2.0, seeded["p1"].lng - 0.5
    ngo = _mkuser(db, "ngo@test.in", "ngo", org_id=seeded["ngo"].id, state_code="DL")
    ngo2 = _mkuser(db, "ngo2@test.in", "ngo", org_id=seeded["ngo2"].id, state_code="DL")
    ben = _mkuser(db, "ben@test.in", "beneficiary")
    db.commit()
    return {"dosje": dosje, "state": state, "pmu": pmu, "meena": meena,
            "ngo": ngo, "ngo2": ngo2, "ben": ben}


@pytest.fixture()
def auth(client, users):
    """Token helpers: auth.bearer(role) and auth.headers(role)."""

    def bearer(role: str) -> str:
        email = {"dosje": "dosje@test.in", "state": "state@test.in",
                 "pmu": "rakesh@test.in", "meena": "meena@test.in",
                 "ngo": "ngo@test.in", "ngo2": "ngo2@test.in",
                 "ben": "ben@test.in"}[role]
        resp = client.post("/api/auth/login",
                           json={"email": email, "password": "Passw0rd!x"})
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    class Helper:
        def headers(self, role: str) -> dict:
            return {"Authorization": f"Bearer {bearer(role)}"}

        def action(self, role: str) -> dict:
            """Headers including a re-authentication action token."""
            email = {"dosje": "dosje@test.in", "state": "state@test.in"}[role]
            h = self.headers(role)
            resp = client.post("/api/auth/confirm-password",
                               json={"password": "Passw0rd!x"}, headers=h)
            assert resp.status_code == 200, resp.text
            h["X-Action-Token"] = resp.json()["action_token"]
            return h

    return Helper()
