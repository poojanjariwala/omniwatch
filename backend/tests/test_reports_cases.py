"""Case workflow and evidence-backed dossier generation (FR-15/16)."""
from __future__ import annotations


def _make_alert(db, project) -> None:
    from app.services import alerts as alert_svc
    alert_svc.create_alert(
        db,
        kind="activity_surge", severity="critical",
        title="Sudden activity surge",
        summary="Occupancy 3.9x the project baseline in a short window.",
        project=project,
        signals=[{"type": "cctv_occupancy", "observed": 40, "baseline_ewma": 10.2}],
        risk_signal=0.9,
        recommended_action="Verify with a blind surprise inspection.",
        ai_generated=True,
    )
    db.commit()


def test_case_open_close_and_dossier(client, auth, seeded, users):
    from app.db import SessionLocal
    from app.models.ops import Alert, Case, Project
    db = SessionLocal()
    try:
        p = db.get(Project, seeded["p1"].id)
        _make_alert(db, p)
        alert = db.query(Alert).filter(Alert.project_id == p.id).first()
        alert_id = alert.id
    finally:
        db.close()

    opened = client.post(f"/api/cases?alert_id={alert_id}&note=investigate",
                         headers=auth.headers("dosje"))
    assert opened.status_code == 200, opened.text
    case_code = opened.json()["case_code"]
    case_id = opened.json()["case_id"]

    detail = client.get(f"/api/cases/{case_id}", headers=auth.headers("dosje"))
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["case"]["code"] == case_code
    assert len(payload["alerts"]) == 1
    assert any(t["kind"] == "alert" for t in payload["timeline"])

    # Dossier generation requires re-authentication.
    no_token = client.get(f"/api/cases/{case_id}/report",
                          headers=auth.headers("dosje"))
    assert no_token.status_code == 403
    pdf = client.get(f"/api/cases/{case_id}/report",
                     headers=auth.action("dosje"))
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers.get("x-report-sha256")
    assert pdf.content[:5] == b"%PDF-"

    # Close (requires action token too).
    close = client.post(f"/api/cases/{case_id}/close",
                        json={"closure_action": "clear",
                              "closure_note": "Verified — no discrepancy found"},
                        headers=auth.headers("dosje"))
    assert close.status_code == 403
    close = client.post(f"/api/cases/{case_id}/close",
                        json={"closure_action": "clear",
                              "closure_note": "Verified — no discrepancy found"},
                        headers=auth.action("dosje"))
    assert close.status_code == 200, close.text
    assert close.json()["status"] == "closed"
