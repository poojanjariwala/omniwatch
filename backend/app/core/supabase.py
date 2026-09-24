"""Server-side Supabase Auth integration.

The anon key and JWT secret never leave the backend. Clients authenticate with
Supabase and present the Supabase access token; every protected route verifies
that token server-side before loading the local role-aware User row.
"""
from __future__ import annotations

import jwt as pyjwt
import httpx
from fastapi import HTTPException, status

from app.config import settings


class SupabaseError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


def _url(path: str) -> str:
    base = settings.supabase_url.rstrip("/")
    return f"{base}{path}"


def _headers(**extra: str) -> dict:
    if not settings.supabase_anon_key:
        raise SupabaseError("Supabase not configured", 503)
    return {"apikey": settings.supabase_anon_key,
            "Content-Type": "application/json", **extra}


def _auth_call(method: str, path: str, json_body: dict | None = None,
               access_token: str | None = None) -> dict:
    headers = _headers()
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    try:
        resp = httpx.post(_url(path), json=json_body, headers=headers,
                          timeout=20.0) if method == "POST" else \
            httpx.request(method, _url(path), json=json_body, headers=headers, timeout=20.0)
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise SupabaseError(f"Supabase unreachable: {exc}", 502) from exc
    if resp.status_code >= 400:
        detail = "Invalid credentials"
        try:
            body = resp.json()
            if isinstance(body, dict) and body.get("error_description"):
                detail = str(body["error_description"])
            elif isinstance(body, dict) and body.get("msg"):
                detail = str(body["msg"])
        except ValueError:
            pass
        raise SupabaseError(detail, resp.status_code)
    try:
        return resp.json()
    except ValueError as exc:  # pragma: no cover
        raise SupabaseError("Malformed Supabase response", 502) from exc


def sign_in_with_password(email: str, password: str) -> dict:
    """Exchange credentials for a Supabase session (server-side proxy)."""
    return _auth_call("POST", "/auth/v1/token?grant_type=password",
                      {"email": email, "password": password})


def refresh_session(refresh_token: str) -> dict:
    return _auth_call("POST", "/auth/v1/token?grant_type=refresh_token",
                      {"refresh_token": refresh_token})


def sign_out(access_token: str) -> None:
    try:
        _auth_call("POST", "/auth/v1/logout", access_token=access_token)
    except SupabaseError:  # idempotent logout
        pass


def verify_access_token(token: str, secret: str | None = None) -> dict:
    """Verify a Supabase access-token JWT and return its claims.

    `secret` defaults to the configured SUPABASE_JWT_SECRET; passing it explicitly
    keeps the function unit-testable without environment mutation.
    """
    jwt_secret = secret or settings.supabase_jwt_secret
    if not jwt_secret:
        raise SupabaseError("Supabase not configured", 503)
    try:
        claims = pyjwt.decode(
            token, jwt_secret, algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except pyjwt.ExpiredSignatureError as exc:  # noqa: PERF203
        raise SupabaseError("Session expired", 401) from exc
    except pyjwt.InvalidTokenError as exc:
        raise SupabaseError("Invalid session token", 401) from exc
    if not claims.get("sub"):
        raise SupabaseError("Invalid session token", 401)
    return claims


def admin_create_user(email: str, password: str, full_name: str) -> dict:
    """Provision a user via the service-role API (bootstrap scripts only)."""
    if not settings.supabase_service_key:
        raise SupabaseError("SUPABASE_SERVICE_KEY not configured", 503)
    headers = {"apikey": settings.supabase_service_key,
               "Authorization": f"Bearer {settings.supabase_service_key}",
               "Content-Type": "application/json"}
    try:
        resp = httpx.post(
            _url("/auth/v1/admin/users"),
            json={"email": email, "password": password,
                  "email_confirm": True,
                  "user_metadata": {"full_name": full_name, "omniwatch_role_hint": None}},
            headers=headers, timeout=20.0,
        )
    except httpx.HTTPError as exc:  # noqa: BLE001
        raise SupabaseError(f"Supabase unreachable: {exc}", 502) from exc
    if resp.status_code >= 400:
        body = {}
        try:
            body = resp.json()
        except ValueError:
            pass
        message = (body.get("msg") or body.get("message") or
                   "User provisioning failed") if isinstance(body, dict) else "Provisioning failed"
        # 422 / 409 (duplicate) are acceptable during idempotent re-seeding.
        raise SupabaseError(str(message), resp.status_code)
    return resp.json()


def http_exception(exc: SupabaseError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))
