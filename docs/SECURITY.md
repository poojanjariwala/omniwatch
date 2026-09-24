# SECURITY.md

Scope: the OmniWatch MVP. AI output is advisory only — detection and prioritization are
automated; verification, decisions and escalation always belong to authorized officials.

## Authentication

- **Local mode:** Argon2id password hashes (`argon2.PasswordHasher`), automatic rehash on
  login, JWT access (30 min) / refresh (7 d) / action (10 min) token pairs. Refresh tokens
  are stored hashed (SHA-256), rotated on use, and revoked on logout.
- **Supabase mode** (`SUPABASE_URL` + `SUPABASE_JWT_SECRET`): credentials verified by
  Supabase Auth server-side; every protected route verifies the access-token JWT
  (HS256, signature + expiry) and maps it to the local role-aware user row. The JWT
  secret and service key never leave the backend.
- **Re-authentication:** sensitive operations (case closure, inspection completion, PDF
  dossier) require a short-lived `action` token minted only after a fresh password check
  (`POST /api/auth/confirm-password`, `X-Action-Token` header).
- Login timing is equalized with a dummy Argon2 verify for unknown accounts to blunt
  user enumeration. All login/logout/refresh/re-auth events are audited.
- The server refuses to boot in production with the shipped default `SECRET_KEY`
  (JWTs signed by a public default would be forgeable).

## Authorization (RBAC + object-level)

- Roles: `dosje`, `state`, `pmu`, `ngo`, `beneficiary`. Checked server-side on every
  route via `require_roles`; frontend route hiding is never treated as authorization.
- Object-level scope on every sensitive read/write: project access by role and state
  (`can_access_project`), inspector ownership of assignments and evidence, NGO org
  ownership of distributions/events, state-scoped events/distributions/inspectors.
- NGOs can never read alerts, risk scores, inspection schedules or CCTV events (FR-14);
  this is enforced in serializers (`project_public(for_role="ngo")` strips risk) and by
  403s at the routers.
- Authorization failures are audited with actor, path and reason.

## API security

- Rate limits (slowapi, per-IP, env-tunable): login 10/min, refresh 20/min, re-auth
  10/min, upload 30/min, QR scan 30/min, dispatch 20/min, demo scenarios 5/min.
- Strict request validation (Pydantic bounds on every field), bounded list limits
  (`ge=1` clamps), bounded file reads (size checked before processing).
- CORS allow-list; Bearer auth with `allow_credentials=False`.
- Safe errors: handlers return short messages; no stack traces or internals.
- SSRF surface: the backend fetches no client-supplied URLs (CCTV URLs are only used by
  the CV worker as configured stream sources).

## Input & XSS

- All form/API input validated server-side; strings length-capped.
- React escapes output by default; no `dangerouslySetInnerHTML` anywhere in the SPA.
- CSP: strict default (`default-src 'self'`, `frame-ancestors 'none'`, no inline
  scripts); a dev variant exists only while OpenAPI docs are enabled (docs are disabled
  in production). Also `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy: camera=(self), geolocation=(self)`, HSTS opt-in.
- `/api/*` responses are `Cache-Control: no-store`.

## Files & uploads

- Inspection evidence must declare a live camera source; gallery uploads are rejected.
  Offline-queue sync uses a dedicated `offline_synced` source and requires the queue's
  `client_ref`; demo-simulated source is only accepted in demo scope.
- Content sniffing decides the MIME (JPEG/PNG signatures, RIFF+WEBP, MP4/MOV `ftyp`
  box, `%PDF` for reviewer attachments) — declared Content-Type is not trusted.
- Size caps: photos 15 MB, video 60 MB (configurable), read with a +1 byte guard.
- Filenames are server-generated (SHA-256 of bytes); uploads live outside web roots and
  are served only through authorized endpoints (`/api/evidence/{id}/file`), never static.
- Every download and integrity check is audited (`evidence_viewed`, `evidence_downloaded`).

## Database

- SQLAlchemy ORM exclusively (parameterized); no string-built SQL.
- Compose deployment: separate admin (migrate one-shot) and app (DML-only) roles;
  DB not exposed publicly; connections via the internal network.
- SQLite dev mode runs with `PRAGMA foreign_keys=ON` so FK mistakes fail in dev too.

## Logging & audit

- `audit_events` records authentication, authorization failures, admin actions,
  assignment events (nonce + commitment), evidence access, report generation and
  security events. `_sanitize` drops keys containing password/token/secret/api_key.
- Evidence chain-of-custody: `chain_hash = SHA-256(prev_hash || artifact_sha256 ||
  canonical_metadata)`; integrity is recomputable per artifact via `/api/evidence/{id}/verify`.

## Randomization integrity

- CSPRNG (`secrets`) for assignment draws and QR codes; every assignment stores
  nonce + SHA-256 commitment (`assignment_commitment`) for independent re-verification.
- Risk signal biases priority but never guarantees selection; no automatic verdicts.

## Known limitations (deliberate MVP scope)

1. **Evidence source declarations are client-trusted.** "Live camera" and
   "offline_synced" are declared by the app, not cryptographically attested. Real
   Play Integrity / device attestation is the follow-up phase (the `DeviceCheck`
   contract is retained).
2. **Rate limiting is in-memory per process.** Multi-worker deployments need a shared
   store (Redis) for global counters.
3. **Refresh-token reuse detection** revokes the presented token but not the whole
   token family.
4. **Supabase JWT `aud` is not verified** (only signature, expiry and `sub`); enabling
   `verify_aud` against the `authenticated` audience is recommended at hardening.
5. **Demo seed passwords live in source** (`backend/app/bootstrap.py`) — acceptable only
   because every seeded entity is DEMO-prefixed and seeding is off in production.
6. Secrets scanning (`scripts/scan_secrets.py`) is heuristic; rotate anything it flags.
