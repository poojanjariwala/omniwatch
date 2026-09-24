"""Supabase JWT verification primitives (mode-specific token handling)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.core.supabase import SupabaseError, verify_access_token

_SECRET = "supabase-test-jwt-secret-0123456789-adequate-length"


def _supa_token(secret: str, *, exp_delta: timedelta = timedelta(hours=1),
                sub: str = "u-123") -> str:
    now = datetime.now(timezone.utc)
    return pyjwt.encode({
        "iss": "https://xyz.supabase.co/auth/v1",
        "sub": sub, "aud": "authenticated", "role": "authenticated",
        "email": "inspector@example.in", "iat": now,
        "exp": now + exp_delta,
    }, secret, algorithm="HS256")


def test_supabase_token_verifies_and_exposes_claims():
    token = _supa_token(_SECRET)
    claims = verify_access_token(token, secret=_SECRET)
    assert claims["sub"] == "u-123"
    assert claims["email"] == "inspector@example.in"


def test_wrong_secret_is_rejected():
    token = _supa_token("a-different-test-secret-long-enough-to-silence-hmac-warnings")
    try:
        verify_access_token(token, secret=_SECRET)
        raise AssertionError("expected SupabaseError")
    except SupabaseError as exc:
        assert exc.status_code == 401


def test_expired_token_is_rejected():
    token = _supa_token(_SECRET, exp_delta=timedelta(minutes=-5))
    try:
        verify_access_token(token, secret=_SECRET)
        raise AssertionError("expected SupabaseError")
    except SupabaseError as exc:
        assert "expired" in str(exc).lower()
