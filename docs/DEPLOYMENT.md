# OmniWatch — Deployment Guide (Docker Compose)

The full stack ships in this repo. One command deploys everything:
PostGIS database, Redis, FastAPI API, Celery worker + beat, and an nginx
container that serves the built frontend and proxies `/api`.

Verified working end-to-end on 2026-09-23 (scenario A + PMU task flow on the
deployed stack, 25/25 backend tests green).

## 1. Prerequisites

- Docker Desktop (Windows) running — start it, then wait for `docker info` to
  succeed.
- Nothing else: Python/Node are only needed for local dev, not for deploy.

## 2. Configure secrets (once)

```bash
cp .env.example .env          # then edit .env
```

Minimum values to replace (never commit the real file — `.gitignore` already
excludes `.env`):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing (≥ 32 chars, e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `OMNIWATCH_ADMIN_PASSWORD` | Postgres admin role (used by migrate) |
| `OMNIWATCH_APP_PASSWORD` | Postgres least-privilege app role (DML only) |
| `OMNIWATCH_SEED_ON_START` | `true` loads the idempotent DEMO dataset + demo logins; set `false` for an empty, production-like deploy |

## 3. Deploy

```bash
docker compose build          # first build downloads base images (slow networks: see Troubleshooting)
docker compose up -d          # db → redis → migrate → api/worker/beat/web
curl http://localhost:8080/api/health
```

Open **http://localhost:8080** — nginx serves the built SPA and proxies `/api`.
Demo logins are printed by the seed and listed in the README.

Stop / reset:

```bash
docker compose down           # stop (keeps data)
docker compose down -v        # stop AND wipe database + uploads (fresh reseed)
```

## 4. What the stack runs

| Service | Image / build | Role |
|---|---|---|
| `db` | postgis/postgis:16-3.4 | PostGIS; not published to the host (internal only) |
| `redis` | redis:7-alpine | Celery broker/result backend |
| `migrate` | backend.Dockerfile | One-shot DDL as admin + grants to app role |
| `api` | backend.Dockerfile | FastAPI, DML-only DB role, `AUTO_CREATE_TABLES=false` |
| `worker` / `beat` | backend.Dockerfile | Celery CCTV ingestion pipeline |
| `web` | web.Dockerfile | Multi-stage Vite build served by nginx; CSP + security headers |

## 5. Deploy-blocking bugs fixed (2026-09-23)

These were real defects in the repo's deploy path — a fresh `docker compose up`
could never have succeeded before them:

1. **DB init script crashed and poisoned the volume.**
   `infra/db/init/01-users.sql` ran `CREATE ROLE omniwatch_admin ...` but the
   image already creates that superuser from `POSTGRES_USER` → duplicate-role
   error aborted init (`ON_ERROR_STOP`), `omniwatch_app` was never created, and
   because Postgres skips `/docker-entrypoint-initdb.d` once a datadir exists,
   every retry stayed broken. Replaced with idempotent
   `infra/db/init/01-users.sh` (checks `pg_roles`, uses `"$POSTGRES_USER"` and
   the `OMNIWATCH_APP_PASSWORD` passed through the `db` service environment).

2. **`migrate` created no tables while reporting success.**
   `app/migrate.py` called `Base.metadata.create_all` without importing
   `app.models`, so metadata was empty (routers import models only later, which
   is why dev mode worked). Added `import app.models` — migrate now creates all
   21 tables and applies the DML grants.

3. **API crashed doing DDL it must not do.**
   The api role is DML-only (least privilege); the API's
   `auto_create_tables=True` dev default made startup fail with
   `permission denied for schema public`. Compose now sets
   `AUTO_CREATE_TABLES=false` for `api` and `worker` — schema changes belong to
   the one-shot `migrate` service only.

4. **nginx cached a dead api IP → random 502s.**
   nginx resolves upstreams once at startup; after the api container is
   recreated (new IP) `/api` 502s until nginx restarts. `infra/nginx.conf` now
   resolves per-request via Docker DNS
   (`resolver 127.0.0.11 valid=10s; set $api_upstream http://api:8000;`).

5. **Flaky-network resilience (build).** `PIP_DEFAULT_TIMEOUT=120` and
   `PIP_RETRIES=10` added to `infra/backend.Dockerfile` after a PyPI read
   timeout killed a build mid-install.

## 6. Troubleshooting

- **Slow Docker Hub / PyPI (builds crawl or die):** rerun `docker compose
  build` — completed layers are cached, so it resumes. If pulls stall, pull
  bases separately first (`docker pull postgis/postgis:16-3.4` etc.).
- **502 on `/api` only:** `docker compose restart web` (should no longer be
  needed after fix 4), then `docker compose logs api`.
- **"role omniwatch_app does not exist" or stale schema:** the db volume was
  initialized before the fixes — `docker compose down -v && docker compose up -d`
  (wipes demo data; reseed is automatic with `OMNIWATCH_SEED_ON_START=true`).
- **Verify schema quickly:** `docker compose exec db psql -U omniwatch_admin -d
  omniwatch -c "\dt"` should list ~21 tables.
- **LAN access:** ensure port 8080 is reachable (`http://<PC-IP>:8080`); Windows
  Firewall may prompt on first external request.
