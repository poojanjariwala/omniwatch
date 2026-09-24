"""Rate limiting (slowapi) — login, refresh, re-auth, upload, QR, dispatch.

Limits are read from settings so deployments can tune them per environment;
the defaults are deliberately strict (brute-force / abuse guards).
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=False,  # FastAPI routes return dicts; header injection is incompatible
    storage_uri="memory://",
)

# Named route limits per IP.
LOGIN_LIMIT = settings.rate_login
REFRESH_LIMIT = settings.rate_refresh
ACTION_LIMIT = settings.rate_action
UPLOAD_LIMIT = settings.rate_upload
QR_SCAN_LIMIT = settings.rate_qr_scan
DISPATCH_LIMIT = settings.rate_dispatch
