"""Authentication, authorization and role-blindness (security gate part 1)."""
from __future__ import annotations


def _login(client, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_login_success_and_failure(client, users):
    ok = _login(client, "dosje@test.in", "Passw0rd!x")
    assert ok.status_code == 200
    assert ok.json()["access_token"] and ok.json()["refresh_token"]
    bad = _login(client, "dosje@test.in", "wrong-password!")
    assert bad.status_code == 401


def test_ngo_cannot_see_alerts_or_cctv(client, auth):
    assert client.get("/api/alerts", headers=auth.headers("ngo")).status_code == 403
    assert client.get("/api/cctv", headers=auth.headers("ngo")).status_code == 403
    assert client.get("/api/dashboard/overview", headers=auth.headers("ngo")).status_code == 403
    assert client.get("/api/audit", headers=auth.headers("ngo")).status_code == 403


def test_audit_is_officials_only(client, auth):
    assert client.get("/api/audit", headers=auth.headers("state")).status_code == 403
    assert client.get("/api/audit", headers=auth.headers("dosje")).status_code == 200


def test_role_blindness_on_project_fields(client, auth, seeded):
    """NGO responses must never include risk fields (data blindness)."""
    p = seeded["p1"]
    ngo_resp = client.get(f"/api/projects/{p.id}", headers=auth.headers("ngo"))
    assert ngo_resp.status_code == 200
    ngo_proj = ngo_resp.json()
    assert "risk_score" not in ngo_proj and "risk_status" not in ngo_proj
    dosje_proj = client.get(f"/api/projects/{p.id}",
                            headers=auth.headers("dosje")).json()
    assert "risk_score" in dosje_proj and "risk_status" in dosje_proj


def test_cross_org_denial(client, auth, seeded):
    """NGO may not touch another organisation's project data."""
    other = seeded["p2"]  # owned by ngo2
    resp = client.get(f"/api/projects/{other.id}", headers=auth.headers("ngo"))
    assert resp.status_code == 404
    # Cross-org QR scan is refused.
    assert client.post("/api/qr/batches",
                       json={"project_id": other.id, "title": "Cross org",
                             "count": 1},
                       headers=auth.headers("ngo")).status_code == 403


def test_idor_inspection_hidden_from_other_pmu(client, auth, seeded, users):
    """An inspector cannot see another inspector's sealed assignment."""
    from app.db import SessionLocal
    from app.services.dispatch import pick_and_assign
    db = SessionLocal()
    try:
        insp, _, _ = pick_and_assign(db, project=seeded["p1"], actor=users["dosje"],
                                     kind="scheduled")
        insp_id = insp.id
    finally:
        db.close()
    # Rakesh (owner) sees it; Meena (different inspector) does not.
    assert client.get(f"/api/inspections/{insp_id}",
                      headers=auth.headers("pmu")).status_code == 200
    assert client.get(f"/api/inspections/{insp_id}",
                      headers=auth.headers("meena")).status_code in (403, 404)
