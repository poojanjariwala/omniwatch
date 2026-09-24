# OmniWatch — Permanent Public Hosting (Netlify + Render + Supabase, free tiers)

Netlify/Vercel host **only the frontend** — OmniWatch also needs a Python API
and a database, so the permanent setup is a three-piece split. All three have
free tiers and give permanent URLs (unlike the local cloudflared tunnel).

| Piece | Host | URL you get |
|---|---|---|
| Frontend (this repo `web/`) | Netlify | `https://omniwatch.netlify.app` |
| API (FastAPI in Docker) | Render | `https://omniwatch-api.onrender.com` |
| Database | Supabase (Postgres) | pooler connection string |

Config files already in the repo: `netlify.toml` (build + `/api` proxy),
`vercel.json` (Vercel alternative), `render.yaml` (Render blueprint).

## 0. One-time: put the repo on GitHub

The folder is not a git repository yet. From the project root:

```bash
git init
git add .
git commit -m "OmniWatch initial commit"
# create an empty repo named omniwatch on github.com, then:
git remote add origin https://github.com/<your-user>/omniwatch.git
git push -u origin main
```

`.gitignore` already excludes `.env`, uploads, venvs and node_modules — verify
with `git status` before pushing (no secrets should be listed).

## 1. Database — Supabase (5 min)

1. supabase.com → New project (any name, e.g. `omniwatch`); save the DB
   password.
2. Project Settings → Database → Connection string → **URI** with the
   **connection pooler** (port 6543, `db.<ref>.supabase.co`).
3. Convert it to a SQLAlchemy URL — add the driver and change the port:

   ```
   postgresql+psycopg2://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```

Keep this URL for step 2. (Server-side only — never in the frontend.)

## 2. API — Render (10 min)

1. dashboard.render.com → **New + → Blueprint**, pick the GitHub repo — it
   reads `render.yaml`.
2. When prompted, paste the Supabase URL as `DATABASE_URL`.
3. Deploy. First boot runs migrations-compatible table creation, seeds the DEMO
   dataset (logins in README) and exposes `/api/health`.
4. Note the service URL — it must be `https://omniwatch-api.onrender.com` to
   match the frontend proxy (or rename and edit `netlify.toml` accordingly).

Free-tier behaviour: sleeps after ~15 min idle → first visitor waits ~50 s.
A free uptime pinger (cron-job.org) hitting `/api/health` every 10 min keeps
it warm.

## 3. Frontend — Netlify (5 min)

1. app.netlify.com → **Add new site → Import an existing project** → pick the
   GitHub repo. Netlify reads `netlify.toml` automatically:
   - build: `npm run build` in `web/`, publish `web/dist`
   - `/api/*` proxied (same-origin) to the Render service.
2. If the site name isn't `omniwatch`, either rename it in Site settings →
   Change site name, or update the Render URL inside `netlify.toml` and push.

### Vercel instead?

Import the same repo into Vercel — `vercel.json` provides the equivalent
`/api` rewrite. Use one or the other; both files can coexist harmlessly.

## 4. Verify

```bash
curl https://<your-netlify-site>.netlify.app/api/health
# -> {"status":"ok",...}
```

Then open the site and log in with the demo accounts (README). Camera and GPS
work on the deployed URL because it is HTTPS.

## Why this architecture

- `web/src/lib/api.ts` calls the API with **relative paths only** — no code
  changes needed once `/api` is proxied same-origin.
- CSP in `web/index.html` (`connect-src 'self'`) keeps working because the
  browser never talks to Render directly.
- No Celery/Redis on free tiers: the backend falls back to inline CV ingestion
  (`.env.example` documents this); `CV_MODE=sim` avoids YOLO weight downloads.
- Geo checks are plain Python (haversine), not PostGIS SQL — Supabase's plain
  Postgres is sufficient.

## Updating

Push to `main` → both Netlify and Render rebuild automatically. No manual
steps.
