# OMNIWATCH

**From Self-Reported Monitoring to Evidence-Backed Verification.**

A centralized DoSJE monitoring and inspection platform (SIH 2026, PS 26095): evidence-backed
project monitoring, cryptographically auditable random inspections, blind assignment,
geo-bound field evidence with a hash chain-of-custody, and a human-in-the-loop case workflow.

Core flow: **MONITOR → DETECT → RANDOMIZE → VERIFY → CAPTURE → AUDIT → ACT**

---

## Repository layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI + SQLAlchemy API, CV pipeline, Celery workers, tests |
| `web/` | React + TypeScript control-room UI (Vite) |
| `infra/` | Dockerfiles, nginx config, Postgres init |
| `scripts/` | `seed_demo.py`, `scan_secrets.py` |
| `docs/` | SECURITY.md, API_INVENTORY.md, TRACEABILITY.md, DEMO_SCRIPT.md |

## Quickstart (local dev, no Docker)

Prerequisites: Python 3.10+, Node 20+.

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt          # macOS/Linux
DEMO_MODE=true DEBUG=true SEED_ON_START=true .venv/Scripts/python -m uvicorn app.main:app --port 8000

# Frontend (second terminal)
cd web
npm install
npm run dev          # http://localhost:5173
```

First start seeds a SAMPLE dataset (demo projects, cameras with warmed baselines,
QR batches, an outdoor event). The UI shows a persistent **DEMO MODE** banner.

### Demo logins

| Role | Email | Password |
|---|---|---|
| DoSJE official | `admin@omniwatch.demo.in` | `Admin@Demo123` |
| State authority | `state@omniwatch.demo.in` | `State@Demo123` |
| Inspector (PMU) | `rakesh@pmu.demo.in` / `meena@pmu.demo.in` | `Pmu@Demo123` |
| NGO | `ngo@demo.org` / `ngo2@demo.org` | `Ngo@Demo123` / `Ngo2@Demo123` |
| Beneficiary | `ben@demo.in` | `Ben@Demo123` |

## Docker composition (Postgres/PostGIS + Redis + Celery)

```bash
cp .env.example .env   # replace every CHANGE-ME value first
docker compose up --build
```

Services: `db` (PostGIS, least-privilege app role), `redis`, `api`, `worker` (Celery
CCTV ingestion cadence), `beat`, `web` (nginx + built SPA). The one-shot `migrate`
step creates the schema with the admin URL, then grants the app role DML only.

## Supabase mode

Set `SUPABASE_URL` + `SUPABASE_JWT_SECRET` (+ `SUPABASE_SERVICE_KEY` for seeding)
and `DATABASE_URL` at the Supabase Postgres pooler. Credentials are then verified by
Supabase Auth server-side; every protected route verifies the access-token JWT and maps
it to the local role-aware user row. RBAC stays in the application database. Without
these variables the backend falls back to local Argon2id + its own JWT pairs.

## Demo scenarios

Run from the government dashboard (or `POST /api/demo/scenario/{a,b,c}` as the DoSJE
user; requires `DEMO_MODE=true`):

- **A — Sudden surge:** CCTV spike → explainable tip-off alert → blind inspection dispatch.
- **B — QR replay:** consume an item QR, replay it → blocked server-side, alert raised.
- **C — Outdoor event:** 48-h+ registration → approval → live broadcast → spot-check dispatch.

Full walkthrough: `docs/DEMO_SCRIPT.md`.

## Tests & checks

```bash
cd backend && .venv/Scripts/python -m pytest -q      # 25 tests: RBAC/IDOR, geofence,
                                                     # QR replay, chain integrity, auth modes
cd web && npx tsc --noEmit && npx vite build
python scripts/scan_secrets.py --history             # secret scan (values never printed)
```

## Documentation

- `docs/SECURITY.md` — security model, controls, known limitations
- `docs/API_INVENTORY.md` — every endpoint, role gate and rate limit
- `docs/TRACEABILITY.md` — PRD flaw → mechanism → proof matrix
- `docs/DEMO_SCRIPT.md` — judge/demo walkthrough for scenarios A/B/C
