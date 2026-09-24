# Traceability matrix — problem → mechanism → proof

Every real-world flaw the PRD targets maps to a demonstrable mechanism and a
reproducible proof (test or demo step). "Demo" steps reference `docs/DEMO_SCRIPT.md`.

| # | Flaw in self-reported monitoring | OmniWatch mechanism | Proof |
|---|---|---|---|
| 1 | Inflated attendance / staged activity | CV pipeline (YOLOv8+ByteTrack or deterministic simulator) → EWMA adaptive baseline → explainable surge / tip-off alert | Demo A; `tests/test_demo_scenarios.py`; baseline outlier rejection in `cv/anomaly.py` |
| 2 | Predictable inspections | CSPRNG draw with recorded nonce + SHA-256 commitment; hybrid random+risk priority | commitment verified in `test_dispatch_is_blind_and_auditable`; `core/randomization.py` |
| 3 | Inspector forewarned / proxy visits | Blind assignment envelope — project intelligence released only at activation after device check; same-day `/inspections/mine` shows no project data | `test_dispatch_is_blind_and_auditable`, `test_activation_requires_device_check` |
| 4 | Fake field presence | Server-side haversine geofence (50 m reference), GPS heartbeats, arrival correlation | `test_geofence.py`, `test_full_geo_evidence_flow` (in/out fence) |
| 5 | Gallery photos passed off as field evidence | Live-camera-only rule server-side; content sniffing; server-generated filenames | `test_evidence_input_validation`, gallery 422 in `test_full_geo_evidence_flow` |
| 6 | Evidence tampering | Per-artifact SHA-256 + linked chain-of-custody, recomputable integrity endpoint | `test_full_geo_evidence_flow` (chain linkage), `/api/evidence/{id}/verify` |
| 7 | Repeated/replayed distribution claims | Atomic consume (`UPDATE … WHERE status='issued'`), replay blocked + alerted, duplicate-recipient binding | `test_consume_then_replay_is_blocked`, `test_duplicate_recipient_alert`, Demo B |
| 8 | Unregistered outdoor events | 48-h advance GPS registration, approval, event-day live broadcast, random spot-check | Demo C; 48-h rule in `services/events.py` |
| 9 | Self-reports contradicting observations | Cross-channel reconciliation (QR + CCTV vs reported beneficiaries) | `reconcile_project` in `cv/engine.py` |
| 10 | Undisclosed NGO risk gaming | Role separation: NGOs never receive risk scores, alerts or schedules (serializer + router enforcement) | `test_auth_rbac.py`, `test_ngo_scan_logs_show_reasons_but_no_risk` |
| 11 | Weak/absent audit trail | `audit_events` on auth, authz failures, assignments, evidence access, reports; EOD + case PDF dossiers with SHA-256 | `test_reports_cases.py`, `/api/audit` |
| 12 | AI overreach / false accusation | AI = detect + prioritize only; alerts carry what/when/where/signals/recommended verification; decisions need human re-auth | feedback loop in `test_reports_cases.py`; alert schema |
| 13 | Offline field capture lost | Offline queue with `client_ref` idempotent sync | `test_evidence_input_validation` (offline_synced path), `web/src/lib/offline.ts` |
| 14 | Assignment gaming / workload capture | Eligibility constraints: workload cap 3, radius pool, recorded `DispatchRecord` rationale | `services/dispatch.py`; Demo A rationale output |
| 15 | Route falsification (timestamps) | Route integrity: evidence/activation/arrival/submission time correlation → warnings on submit | `_route_integrity`; warnings asserted in `test_full_geo_evidence_flow` |

## Coverage statement

All three PRD demo scenarios run end-to-end against the seeded SAMPLE dataset
(verified live: tip-off alert risk 0.84 → blind dispatch; QR replay blocked;
outdoor event registration → broadcast → spot-check). All 25 backend tests pass;
the frontend typechecks and builds clean.
