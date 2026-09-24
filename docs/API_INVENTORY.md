# API inventory

All routes are prefixed `/api`. Authentication: `Authorization: Bearer <access-token>`.
Roles: **D** dosje · **S** state · **P** pmu · **N** ngo · **B** beneficiary.
Rate-limited routes are marked ⏱. Demo routes only exist when `DEMO_MODE=true`.

## Health
| Method | Path | Access |
|---|---|---|
| GET | `/health` | public |

## Auth (`/auth`)
| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/auth/login` ⏱ | public | local Argon2id or Supabase proxy |
| POST | `/auth/refresh` ⏱ | public | rotation + revocation (local mode) |
| GET | `/auth/me` | any authenticated | |
| POST | `/auth/confirm-password` ⏱ | any authenticated | issues short-lived action token |
| POST | `/auth/logout` | any authenticated | revokes refresh token |

## Organizations & projects
| Method | Path | Access |
|---|---|---|
| GET | `/orgs` | D, S (scoped), P, N (own) |
| GET | `/projects` | D, S, P, N (scoped) |
| POST | `/projects` | D |
| GET | `/projects/{id}` | scoped |
| PATCH | `/projects/{id}` | D |
| GET | `/projects/{id}/overview` | scoped |

## Dashboard
| Method | Path | Access |
|---|---|---|
| GET | `/dashboard/overview` | D, S (state-scoped) |
| GET | `/dashboard/map` | D, S (state-scoped) |
| GET | `/dashboard/ngo-overview` | N (no risk/alert/schedule fields) |

## Alerts (`/alerts`) — government surface, never NGO
| Method | Path | Access |
|---|---|---|
| GET | `/alerts` | D, S (scoped) |
| GET | `/alerts/{id}` | D, S |
| PATCH | `/alerts/{id}/status` | D, S (state machine enforced) |
| POST | `/alerts/{id}/feedback` | D (model feedback TP/FP/inconclusive) |
| POST | `/alerts/{id}/case` | D |
| POST | `/alerts/{id}/dispatch` | D, S (opens blind inspection) |

## CCTV (`/cctv`)
| Method | Path | Access |
|---|---|---|
| GET | `/cctv` | D, S, P (scoped) |
| POST | `/cctv` | D |
| PATCH | `/cctv/{id}` | D |
| POST | `/cctv/{id}/toggle` | D |
| GET | `/cctv/{id}/events` | D, S, P (scoped) |
| POST | `/cctv/{id}/ingest` ⏱ | D (manual cycle; beat cadence in production) |
| GET | `/cctv/events` | D, S, P (scoped) |

## Inspections (`/inspections`)
| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/inspections/dispatch` ⏱ | D, S | auditable random/hybrid draw |
| GET | `/inspections` | D, S (scoped) | |
| GET | `/inspections/mine` | P | blind envelope view |
| GET | `/inspections/{id}` | D, S, P (own) | blind until activation |
| POST | `/inspections/{id}/device-check` | P (own) | pre-activation integrity verdict |
| POST | `/inspections/{id}/activate` | P (own) | requires passing device check |
| POST | `/inspections/{id}/start` | P (own) | |
| POST | `/inspections/{id}/location` | P (own) | server-side geofence validation |
| POST | `/inspections/{id}/checklist` | P (own) | |
| POST | `/inspections/{id}/submit` | P (own) | route-integrity warnings computed |
| POST | `/inspections/{id}/complete` ⏱ | D, S + action token | human decision |
| POST | `/inspections/{id}/evidence` ⏱ | P (own) | live camera only; hash-chained |

## Evidence (`/evidence`)
| Method | Path | Access |
|---|---|---|
| GET | `/evidence` | D, S, P (scoped; P own) |
| GET | `/evidence/{id}` | scoped (integrity recomputed) |
| GET | `/evidence/{id}/file` | scoped, audited download |
| POST | `/evidence/{id}/verify` | scoped |

## QR (`/qr`)
| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/qr/batches` | D, S (scoped), N (own org) | 1–5000 codes per batch |
| GET | `/qr/distributions` | D, S (scoped), N (own) | |
| GET | `/qr/distributions/{id}/codes` | D, S (scoped), N (own) | |
| POST | `/qr/scan` ⏱ | D, S, P, N | atomic consume; replays blocked + alerted |
| GET | `/qr/scan-logs` | D, S (scoped), N (own) | no risk fields for N |
| POST | `/qr/verify` | N, B, D, S, P | read-only status check |

## Outdoor events (`/events`)
| Method | Path | Access | Notes |
|---|---|---|---|
| POST | `/events` | N (own org), D, S | ≥48 h advance rule |
| GET | `/events`, `/events/{id}` | N (own), D, S (scoped) | |
| POST | `/events/{id}/approve` · `/complete` · `/flag` | D, S | |
| POST | `/events/{id}/cancel` | N (own), D, S | |
| POST | `/events/{id}/broadcast` | N (own), D, S | event-day live GPS proof |
| POST | `/events/{id}/spot-check` | D, S | random spot-check dispatch |

## Cases & reports
| Method | Path | Access |
|---|---|---|
| GET | `/cases` | D, S (scoped) |
| POST | `/cases` | D (from alert) |
| GET | `/cases/{id}` | D, S, P (scoped; P own) |
| POST | `/cases/{id}/close` | D, S + action token |
| POST | `/cases/{id}/evidence` | D, S, P (scoped) |
| GET | `/cases/{id}/report` | D, S + action token (PDF dossier, SHA-256) |
| GET | `/audit` | D (audit trail) |
| POST | `/reports/eod` | D (end-of-day dossier) |
| GET | `/reports/eod`, `/reports/eod/{id}/file` | D |

## Demo (`/demo`, DEMO_MODE only)
| Method | Path | Access |
|---|---|---|
| POST | `/demo/scenario/a` ⏱ | D |
| POST | `/demo/scenario/b` ⏱ | D |
| POST | `/demo/scenario/c` ⏱ | D |

*Unused endpoints:* none known; this inventory is the reference for removal review.
