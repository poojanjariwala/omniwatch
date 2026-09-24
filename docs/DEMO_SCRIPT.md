# Demo script — scenarios A, B, C

Prerequisite: backend running with `DEMO_MODE=true SEED_ON_START=true` and the web app
on `http://localhost:5173`. Logins are in the README. All data is SAMPLE data.

## A — Sudden surge (CCTV → alert → blind inspection → field verification)

1. Sign in as **DoSJE official** → Command dashboard.
2. Run scenario A: `POST /api/demo/scenario/a` (or the dashboard's demo control).
   The simulator replays a healthy window then a ramp to ~41 occupants.
3. A **CRITICAL tip-off alert** appears (risk ≈ 0.84) with what/where/when, the CCTV
   ratio vs the adaptive baseline, and a recommended verification — never a verdict.
4. Open **Inspections & dispatch** — a blind `random_surge` inspection was drawn with
   a recorded rationale ("randomised draw … hybrid of uniform randomness and validated
   risk … preserves unpredictability").
5. Sign in as the assigned **Inspector** → My assignments. The task shows **no project
   intelligence**. Run device check → Activate (envelope opens) → Start.
6. Report location (inside 50 m geofence → arrival recorded), capture **live camera**
   evidence (geo-bound, hash-chained), complete the checklist, Submit.
7. Back as DoSJE: review evidence + route warnings in the **Evidence console**, then
   Complete with the re-authentication prompt — the alert feedback (TP/FP) is recorded.

## B — QR replay (duplicate distribution blocked)

1. As DoSJE run `POST /api/demo/scenario/b`.
2. First scan succeeds (`ok: true`), the replay of the same item QR is blocked
   (`ok: false, reason: "consumed"`) — structurally, via an atomic conditional update.
3. A `qr_replay` alert is raised **visible to government roles only**; the NGO terminal
   shows no alert or risk data (FR-14).
4. Optional: log in as the NGO and rescan the same code — blocked again, same alert
   (cooldown prevents queue spam).

## C — Outdoor event (registration → broadcast → spot-check)

1. As DoSJE run `POST /api/demo/scenario/c`.
2. The seeded event was registered **72 h ahead** (the 48-h rule rejects shorter
   notice for NGOs — visible by attempting a 2-h-ahead registration from
   **NGO → Outdoor events**).
3. Government approves → NGO broadcasts live GPS on event day → status `active`.
4. A random spot-check inspection is dispatched; the inspector flow is identical to A.

## End-to-end proof points to call out

- Every dispatch, activation, evidence item and decision is in **Audit log**.
- Evidence integrity: `/api/evidence/{id}` recomputes the SHA-256 and the chain hash.
- Case closure and the PDF dossier both demand password **re-authentication**.
