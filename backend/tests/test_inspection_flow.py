"""Inspector field flow: blind assignment → activation → geo evidence → submit."""
from __future__ import annotations


def _tiny_jpeg() -> bytes:
    # 1x1 JPEG (magic bytes FF D8 FF ...)
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r"
            b"\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \","
            b"#\x1c\x1c\x277\x1d\x1d*+/+\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00"
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03"
            b"\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A"
            b"\x06\x13Qa\x07\"q\x142\x91\xa1\xb4\xc1\xa2\xb2\xd1#R\x81\x08\x14B\x91\xa2\xb1\xc1"
            b"\x15#R\xd1\xf0C3\x92\xa3b\xe1\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd0\x9f\xff"
            b"\xd9")


def _dispatch(client, auth, project_id: int) -> dict:
    resp = client.post("/api/inspections/dispatch",
                       json={"project_id": project_id, "kind": "scheduled",
                             "reason": "Test dispatch"},
                       headers=auth.headers("dosje"))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_dispatch_is_blind_and_auditable(client, auth, seeded, users):
    """Inspector sees no project intelligence until activation."""
    body = _dispatch(client, auth, seeded["p1"].id)
    insp = body["inspection"]
    assert insp["blind"] is True  # official dispatch sees full detail + blind flag
    mine = client.get("/api/inspections/mine", headers=auth.headers("pmu"))
    assert mine.status_code == 200
    my_rows = mine.json()["assignments"]
    assert any(r["code"] == insp["code"] for r in my_rows)
    blind_row = next(r for r in my_rows if r["code"] == insp["code"])
    assert blind_row["blind"] is True
    assert "project" not in blind_row
    # Commitment recorded; method hybrid/random + nonce present.
    assert body["assignment"]["commitment"] and body["assignment"]["nonce"]
    from app.core.randomization import assignment_commitment
    assert body["assignment"]["commitment"] == assignment_commitment(
        body["assignment"]["nonce"], insp["code"],
        body["assignment"]["ts"])


def test_activation_requires_device_check(client, auth, seeded):
    body = _dispatch(client, auth, seeded["p1"].id)
    insp_id = body["inspection"]["id"]
    h = auth.headers("pmu")
    # Activation without a device check is refused.
    r = client.post(f"/api/inspections/{insp_id}/activate", headers=h)
    assert r.status_code == 403
    check = client.post(f"/api/inspections/{insp_id}/device-check", headers=h)
    assert check.status_code == 200 and check.json()["verdict"] == "pass"
    act = client.post(f"/api/inspections/{insp_id}/activate", headers=h)
    assert act.status_code == 200, act.text
    assert act.json()["project"]["code"] == seeded["p1"].code
    assert act.json()["checklist"]  # category template supplied


def test_full_geo_evidence_flow(client, auth, seeded):
    p = seeded["p1"]
    body = _dispatch(client, auth, p.id)
    insp_id = body["inspection"]["id"]
    h = auth.headers("pmu")
    client.post(f"/api/inspections/{insp_id}/device-check", headers=h)
    client.post(f"/api/inspections/{insp_id}/activate", headers=h)
    start = client.post(f"/api/inspections/{insp_id}/start", headers=h)
    assert start.json()["status"] == "in_progress"

    # Heartbeat inside the geofence -> arrival recorded.
    loc = client.post(f"/api/inspections/{insp_id}/location",
                      json={"lat": p.lat, "lng": p.lng}, headers=h)
    assert loc.json()["within_geofence"] is True
    # Heartbeat 2 km away -> flagged outside.
    far = client.post(f"/api/inspections/{insp_id}/location",
                      json={"lat": p.lat + 0.02, "lng": p.lng}, headers=h)
    assert far.json()["within_geofence"] is False

    # Live evidence inside geofence.
    from datetime import datetime, timezone
    captured = datetime.now(timezone.utc).isoformat()
    files = {"file": ("cap.jpg", _tiny_jpeg(), "image/jpeg")}
    data = {"kind": "photo", "source": "live_camera", "lat": str(p.lat),
            "lng": str(p.lng), "captured_at": captured, "client_ref": "C1"}
    ev = client.post(f"/api/inspections/{insp_id}/evidence",
                     headers=h, data=data, files=files)
    assert ev.status_code == 200, ev.text
    evidence = ev.json()
    assert evidence["geofence_ok"] is True
    assert evidence["chain_hash"] and evidence["sha256"]

    # Evidence far outside the geofence is stored but integrity-flagged.
    data2 = {"kind": "photo", "source": "live_camera", "lat": str(p.lat + 0.05),
             "lng": str(p.lng), "captured_at": captured, "client_ref": "C2"}
    ev2 = client.post(f"/api/inspections/{insp_id}/evidence",
                      headers=h, data=data2,
                      files={"file": ("far.jpg", _tiny_jpeg(), "image/jpeg")})
    assert ev2.status_code == 200
    assert ev2.json()["geofence_ok"] is False

    # Gallery/file-upload claim is rejected outright.
    denied = client.post(f"/api/inspections/{insp_id}/evidence",
                         headers=h,
                         data={"kind": "photo", "source": "gallery",
                               "lat": str(p.lat), "lng": str(p.lng),
                               "captured_at": captured},
                         files={"file": ("gal.jpg", _tiny_jpeg(), "image/jpeg")})
    assert denied.status_code == 422

    sub = client.post(f"/api/inspections/{insp_id}/submit",
                      json={"notes": "Site visited"}, headers=h)
    assert sub.status_code == 200, sub.text
    warnings = sub.json()["route_warnings"]
    assert any("outside the geofence" in w for w in warnings)
    assert any("Checklist" in w for w in warnings)

    # Officials complete the inspection (re-auth action token required).
    complete = client.post(f"/api/inspections/{insp_id}/complete",
                           json={"verification_passed": True,
                                 "decision_notes": "Verified on site"},
                           headers=auth.headers("dosje"))
    assert complete.status_code == 403  # no action token
    complete = client.post(f"/api/inspections/{insp_id}/complete",
                           json={"verification_passed": True,
                                 "decision_notes": "Verified on site"},
                           headers=auth.action("dosje"))
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "completed"

    # Chain-of-custody: hashes link across the two artifacts.
    detail = client.get(f"/api/inspections/{insp_id}",
                        headers=auth.headers("dosje")).json()
    evs = detail["evidence"]
    assert len(evs) == 2
    assert evs[1]["chain_prev_hash"] == evs[0]["chain_hash"]
    # Integrity endpoint recomputes and confirms.
    ok = client.get(f"/api/evidence/{evs[0]['id']}",
                    headers=auth.headers("dosje")).json()
    assert ok["integrity"]["ok"] is True


def test_evidence_input_validation(client, auth, seeded):
    """Content sniffing, timestamp parsing and offline-sync rules fail cleanly."""
    p = seeded["p1"]
    body = _dispatch(client, auth, p.id)
    insp_id = body["inspection"]["id"]
    h = auth.headers("pmu")
    client.post(f"/api/inspections/{insp_id}/device-check", headers=h)
    client.post(f"/api/inspections/{insp_id}/activate", headers=h)
    client.post(f"/api/inspections/{insp_id}/start", headers=h)

    # A file that merely begins with NUL bytes is NOT a video (content sniff).
    junk = b"\x00\x00\x00\x00not-a-video"
    bad = client.post(f"/api/inspections/{insp_id}/evidence", headers=h,
                      data={"kind": "video", "source": "live_camera",
                            "lat": str(p.lat), "lng": str(p.lng)},
                      files={"file": ("junk.mp4", junk, "video/mp4")})
    assert bad.status_code == 422

    # Malformed captured_at is a 422, not a server error.
    bad_ts = client.post(f"/api/inspections/{insp_id}/evidence", headers=h,
                         data={"kind": "photo", "source": "live_camera",
                               "lat": str(p.lat), "lng": str(p.lng),
                               "captured_at": "not-a-date"},
                         files={"file": ("cap.jpg", _tiny_jpeg(), "image/jpeg")})
    assert bad_ts.status_code == 422

    # JS Date.toISOString() emits a trailing 'Z' — must parse on py3.10 too.
    from datetime import datetime, timezone
    z_ok = client.post(f"/api/inspections/{insp_id}/evidence", headers=h,
                       data={"kind": "photo", "source": "live_camera",
                             "lat": str(p.lat), "lng": str(p.lng),
                             "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                             "client_ref": "CZ"},
                       files={"file": ("capz.jpg", _tiny_jpeg(), "image/jpeg")})
    assert z_ok.status_code == 200, z_ok.text

    # The uploading inspector can re-download their own evidence even though
    # PMU users have no org membership (org_id is NULL).
    ev_id = z_ok.json()["id"]
    refetch = client.get(f"/api/evidence/{ev_id}", headers=h)
    assert refetch.status_code == 200, refetch.text
    dl = client.get(f"/api/evidence/{ev_id}/file", headers=h)
    assert dl.status_code == 200, dl.text
    assert dl.content.startswith(b"\xff\xd8")  # the actual JPEG bytes
    # Offline queue sync needs the queue's client_ref, then stores fine.
    from datetime import datetime, timezone
    no_ref = client.post(f"/api/inspections/{insp_id}/evidence", headers=h,
                         data={"kind": "photo", "source": "offline_synced",
                               "lat": str(p.lat), "lng": str(p.lng),
                               "captured_at": datetime.now(timezone.utc).isoformat()},
                         files={"file": ("off.jpg", _tiny_jpeg(), "image/jpeg")})
    assert no_ref.status_code == 422
    synced = client.post(f"/api/inspections/{insp_id}/evidence", headers=h,
                         data={"kind": "photo", "source": "offline_synced",
                               "lat": str(p.lat), "lng": str(p.lng),
                               "captured_at": datetime.now(timezone.utc).isoformat(),
                               "client_ref": "OFF-1"},
                         files={"file": ("off.jpg", _tiny_jpeg(), "image/jpeg")})
    assert synced.status_code == 200, synced.text
    assert synced.json()["source"] == "offline_synced"
    assert synced.json()["geofence_ok"] is True
