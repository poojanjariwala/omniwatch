"""QR lifecycle tests (scenario B / row D2)."""
from __future__ import annotations


def _issue_batch(client, auth, project_id: int, ngo_role="ngo") -> dict:
    resp = client.post("/api/qr/batches",
                       json={"project_id": project_id, "title": "SAMPLE batch",
                             "count": 5},
                       headers=auth.headers(ngo_role))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_consume_then_replay_is_blocked(client, auth, seeded):
    p = seeded["p2"]  # owned by ngo2
    batch = _issue_batch(client, auth, p.id, ngo_role="ngo2")
    code = batch["sample_codes"][0]["code"]
    scan = client.post("/api/qr/scan",
                       json={"code": code, "lat": p.lat, "lng": p.lng},
                       headers=auth.headers("ngo2"))
    assert scan.status_code == 200, scan.text
    assert scan.json()["ok"] is True and scan.json()["reason"] == "success"
    replay = client.post("/api/qr/scan",
                         json={"code": code, "lat": p.lat, "lng": p.lng},
                         headers=auth.headers("ngo2"))
    assert replay.status_code == 200
    assert replay.json()["ok"] is False and replay.json()["reason"] == "consumed"

    # A qr_replay alert was raised — visible to government roles only.
    alerts = client.get("/api/alerts?kind=qr_replay", headers=auth.headers("dosje"))
    assert alerts.status_code == 200
    rows = [a for a in alerts.json()["alerts"] if a["project_id"] == p.id]
    assert rows and rows[0]["severity"] in ("warning", "critical")


def test_duplicate_recipient_alert(client, auth, seeded):
    p = seeded["p2"]
    batch = _issue_batch(client, auth, p.id, ngo_role="ngo2")
    codes = [c["code"] for c in batch["sample_codes"][:2]]
    body = {"recipient_token": "BEN-X", "lat": p.lat, "lng": p.lng}
    first = client.post("/api/qr/scan", json={**body, "code": codes[0]},
                        headers=auth.headers("ngo2")).json()
    assert first["ok"] is True
    second = client.post("/api/qr/scan", json={**body, "code": codes[1]},
                         headers=auth.headers("ngo2")).json()
    assert second["ok"] is True and second["duplicate_recipient"] is True
    alerts = client.get("/api/alerts?kind=duplicate_recipient",
                        headers=auth.headers("dosje")).json()["alerts"]
    assert any(a["project_id"] == p.id for a in alerts)


def test_ngo_scan_logs_show_reasons_but_no_risk(client, auth, seeded):
    p = seeded["p2"]
    batch = _issue_batch(client, auth, p.id, ngo_role="ngo2")
    dist_id = batch["distribution"]["id"]
    code = batch["sample_codes"][0]["code"]
    client.post("/api/qr/scan", json={"code": code, "lat": p.lat, "lng": p.lng},
                headers=auth.headers("ngo2"))
    client.post("/api/qr/scan", json={"code": code, "lat": p.lat, "lng": p.lng},
                headers=auth.headers("ngo2"))
    logs = client.get(f"/api/qr/scan-logs?distribution_id={dist_id}",
                      headers=auth.headers("ngo2"))
    assert logs.status_code == 200
    reasons = {l["reason"] for l in logs.json()["logs"]}
    assert {"success", "consumed"} <= reasons
    body = logs.json()["logs"][0]
    assert "risk" not in body and "signals" not in body


def test_unknown_code_scan_is_handled(client, auth, seeded):
    """Scanning garbage returns a clean not_found, not a server error (FK-safe)."""
    resp = client.post("/api/qr/scan", json={"code": "DEADBEEFCAFE1234"},
                       headers=auth.headers("ngo"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False and body["reason"] == "not_found"


def test_beneficiary_verify_only(client, auth, seeded):
    p = seeded["p2"]
    batch = _issue_batch(client, auth, p.id, ngo_role="ngo2")
    code = batch["sample_codes"][0]["code"]
    client.post("/api/qr/scan", json={"code": code, "lat": p.lat, "lng": p.lng},
                headers=auth.headers("ngo2"))
    check = client.post("/api/qr/verify", json={"code": code},
                        headers=auth.headers("ben"))
    assert check.status_code == 200 and check.json()["status"] == "consumed"
    # Beneficiary cannot scan (consume) items.
    attempt = client.post("/api/qr/scan", json={"code": code},
                          headers=auth.headers("ben"))
    assert attempt.status_code == 403
