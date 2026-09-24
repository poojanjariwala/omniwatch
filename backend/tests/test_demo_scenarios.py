"""End-to-end demo scenario runs (A/B/C) through the /api/demo runner."""
from __future__ import annotations


def _warm_camera(client, auth, project_code: str, project_id: int):
    from app.db import SessionLocal
    from app.models.cv import Camera
    from app.services.cv.engine import ingest_once
    db = SessionLocal()
    try:
        cam = Camera(project_id=project_id, name=f"{project_code} sim",
                     source_type="simulator", ingest_every_seconds=30, enabled=True)
        db.add(cam)
        db.commit()
        for _ in range(6):  # warm adaptive baseline past MIN_SAMPLES
            ingest_once(db, cam)
    finally:
        db.close()
    return cam.id


def test_scenario_a_surge_alert_and_dispatch(client, auth, seeded, users):
    from app.models.ops import Alert
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        from app.models.cv import Camera
        cam = db.query(Camera).filter(Camera.project_id == seeded["p1"].id).first()
    finally:
        pass
    _warm_camera(client, auth, seeded["p1"].code, seeded["p1"].id)

    resp = client.post(f"/api/demo/scenario/a?project_code={seeded['p1'].code}",
                       headers=auth.headers("dosje"))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["alert"] and data["alert"]["code"]
    assert data["ingest"]["flagged"] is True
    # Explainability: signal fields present.
    db = SessionLocal()
    try:
        alert = db.query(Alert).filter(Alert.code == data["alert"]["code"]).first()
        assert alert and alert.signals and alert.recommended_action
        kinds = {s.get("type") for s in alert.signals}
        assert kinds >= {"cctv_occupancy", "what_where_when"}
        # Blind inspection was auto-dispatched (Rakesh is nearest).
        assert data["inspection"] and data["inspection"]["inspector_id"] == \
            seeded["rakesh"].id
    finally:
        db.close()


def test_scenario_b_and_c_flow(client, auth, seeded, users):
    # Ensure batches exist for the demo distribution project.
    h = auth.headers("dosje")
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        from app.models.ops import Distribution
        if db.query(Distribution).filter(
                Distribution.project_id == seeded["p2"].id).count() == 0:
            client.post("/api/qr/batches",
                        json={"project_id": seeded["p2"].id,
                              "title": "demo batch", "count": 6}, headers=h)
    finally:
        db.close()
    b = client.post(f"/api/demo/scenario/b?project_code={seeded['p2'].code}",
                    headers=h)
    assert b.status_code == 200, b.text
    body = b.json()
    assert body["first_scan"]["ok"] is True
    assert body["replay_scan"]["ok"] is False
    assert body["alert_code"]

    # Scenario C needs an 'outdoor' category project; seed p1 as centre works too
    # because demo only needs an enabled camera-less dispatch target. Use a temp
    # outdoor project via direct model creation.
    from app.models.registry import Project
    db = SessionLocal()
    try:
        out = Project(code="TEST-OUT", name="Test Outdoor", scheme="outreach (sample)",
                      category="outdoor", org_id=seeded["ngo2"].id,
                      lat=seeded["p2"].lat + 0.1, lng=seeded["p2"].lng + 0.1,
                      reported_beneficiaries=40)
        db.add(out)
        db.commit()
        out_id = out.id
    finally:
        db.close()
    c = client.post(f"/api/demo/scenario/c?project_code=TEST-OUT", headers=h)
    assert c.status_code == 200, c.text
    assert c.json()["event_code"]
    assert c.json()["step"] in ("approved", "broadcast")
    assert c.json()["inspection"]["code"]
