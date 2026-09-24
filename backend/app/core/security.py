"""Authentication primitives: Argon2id password hashing and signed JWTs."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

_ph = PasswordHasher()

TOKEN_ACCESS = "access"
TOKEN_REFRESH = "refresh"
TOKEN_ACTION = "action"  # short-lived re-authentication proof for sensitive ops


class TokenError(Exception):
    """Raised when a token is invalid, expired or of the wrong type."""


# --- Passwords -----------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, encoded: str) -> bool:
    try:
        return _ph.verify(encoded, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(encoded: str) -> bool:
    try:
        return _ph.check_needs_rehash(encoded)
    except (InvalidHashError, ValueError):  # pragma: no cover
        return True


# --- Tokens --------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_token(user_id: int, role: str, typ: str, ttl_minutes: int) -> str:
    now = _now()
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": typ,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return create_token(user_id, role, TOKEN_ACCESS, settings.jwt_access_ttl_minutes)


def create_refresh_token(user_id: int, role: str) -> str:
    return create_token(user_id, role, TOKEN_REFRESH, settings.jwt_refresh_ttl_days * 24 * 60)


def create_action_token(user_id: int, role: str) -> str:
    return create_token(user_id, role, TOKEN_ACTION, settings.jwt_action_ttl_minutes)


def decode_token(token: str, expected_type: str) -> dict:
    """Decode and validate a JWT. Raises TokenError with a safe message."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:  # noqa: PERF203
        raise TokenError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc
    if payload.get("typ") != expected_type:
        raise TokenError("Token type mismatch")
    return payload


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
