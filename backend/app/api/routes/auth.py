"""Authentication endpoints.

Two modes, selected by configuration:
  * Supabase Auth mode (SUPABASE_URL + SUPABASE_JWT_SECRET set): credentials are
    exchanged with Supabase Auth server-side; every protected route verifies the
    Supabase access-token JWT and maps it to the role-aware local User row.
  * Local mode (no Supabase env): Argon2id hashes + our own JWT pairs, used for
    offline development and the test-suite.

Both modes issue the short-lived *action* token (password re-authentication)
required by highly sensitive endpoints. Refresh tokens are hashed at rest.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core import supabase as sb
from app.core.audit import audit
from app.core.limits import ACTION_LIMIT, LOGIN_LIMIT, REFRESH_LIMIT, limiter
from app.core.rbac import CurrentUser, Db
from app.core.security import (
    TokenError, create_access_token, create_action_token, create_refresh_token,
    decode_token, hash_password, needs_rehash, sha256_hex, TOKEN_REFRESH,
    verify_password,
)
from app.models.users import RefreshToken, User
from app.schemas.serializers import public_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=2000)


class ConfirmIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# Argon2id verification for non-existent users keeps login timing uniform,
# so response time cannot reveal which e-mails are registered.
_DUMMY_HASH = hash_password("omniwatch-timing-equalizer-not-a-login")


def _login_failed(request: Request, db: Session, email: str, reason: str) -> None:
    audit(db, actor_id=None, actor_role=None, action="login_failed",
          object_type="auth", detail={"email": email, "reason": reason},
          ip=_client_ip(request), commit=True)


def _resolve_local_user(db: Session, claims: dict) -> User | None:
    """Map a verified Supabase JWT to our role-aware user row."""
    uid = claims.get("sub")
    email = (claims.get("email") or "").lower()
    if uid:
        user = db.query(User).filter(User.supabase_uid == uid).first()
        if user is not None:
            return user
    if email:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            if uid and not user.supabase_uid:
                user.supabase_uid = uid
                db.commit()
            return user
    return None


def _local_tokens(db: Session, user: User, revoked_hash: str | None = None) -> dict:
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id, user.role)
    h = sha256_hex(refresh)
    db.add(RefreshToken(user_id=user.id, token_hash=h,
                        expires_at=datetime.now(timezone.utc) +
                        timedelta(days=settings.jwt_refresh_ttl_days)))
    if revoked_hash:
        row = db.query(RefreshToken).filter(RefreshToken.token_hash == revoked_hash).first()
        if row:
            row.revoked = True
            row.replaced_by = h
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "provider": "local"}


def _supabase_tokens(session: dict) -> dict:
    return {"access_token": session["access_token"],
            "refresh_token": session.get("refresh_token", ""),
            "token_type": "bearer", "provider": "supabase",
            "expires_at": session.get("expires_at")}


@router.post("/login")
@limiter.limit(LOGIN_LIMIT)
def login(request: Request, body: LoginIn, db: Db):
    email = body.email.lower()
    if settings.supabase_enabled:
        try:
            session = sb.sign_in_with_password(email, body.password)
            claims = sb.verify_access_token(session["access_token"])
        except sb.SupabaseError as exc:
            _login_failed(request, db, email, str(exc))
            raise sb.http_exception(exc) from exc
        user = _resolve_local_user(db, claims)
        if user is None or not user.is_active:
            _login_failed(request, db, email, "account_not_provisioned")
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Account not provisioned for OmniWatch")
        audit(db, actor_id=user.id, actor_role=user.role, action="login",
              object_type="auth", ip=_client_ip(request), commit=True)
        return {"user": public_user(user), **_supabase_tokens(session)}

    # Local fallback (offline dev / tests).
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        verify_password(body.password, _DUMMY_HASH)  # equalise response timing
        _login_failed(request, db, email, "invalid_credentials")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        _login_failed(request, db, email, "invalid_credentials")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.flush()
    tokens = _local_tokens(db, user)
    audit(db, actor_id=user.id, actor_role=user.role, action="login",
          object_type="auth", ip=_client_ip(request), commit=True)
    return {"user": public_user(user), **tokens}


@router.post("/refresh")
@limiter.limit(REFRESH_LIMIT)
def refresh(request: Request, body: RefreshIn, db: Db):
    if settings.supabase_enabled:
        try:
            session = sb.refresh_session(body.refresh_token)
            claims = sb.verify_access_token(session["access_token"])
        except sb.SupabaseError as exc:
            raise sb.http_exception(exc) from exc
        user = _resolve_local_user(db, claims)
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                                detail="Account unavailable")
        audit(db, actor_id=user.id, actor_role=user.role, action="token_refreshed",
              object_type="auth", ip=_client_ip(request), commit=True)
        return _supabase_tokens(session)

    try:
        payload = decode_token(body.refresh_token, TOKEN_REFRESH)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user = db.get(User, int(payload["sub"]))
    h = sha256_hex(body.refresh_token)
    row = db.query(RefreshToken).filter(
        RefreshToken.token_hash == h, RefreshToken.revoked.is_(False)).first()
    if user is None or row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    tokens = _local_tokens(db, user, revoked_hash=h)
    audit(db, actor_id=user.id, actor_role=user.role, action="token_rotated",
          object_type="auth", ip=_client_ip(request), commit=True)
    return tokens


@router.get("/me")
def me(user: CurrentUser):
    return {"user": public_user(user)}


@router.post("/confirm-password")
@limiter.limit(ACTION_LIMIT)
def confirm_password(request: Request, body: ConfirmIn, db: Db, user: CurrentUser):
    """Re-authentication: password proof -> short-lived action token."""
    if settings.supabase_enabled:
        try:
            session = sb.sign_in_with_password(user.email, body.password)
            claims = sb.verify_access_token(session["access_token"])
            mapped = _resolve_local_user(db, claims)
        except sb.SupabaseError as exc:
            audit(db, actor_id=user.id, actor_role=user.role, action="reauth_failed",
                  object_type="auth", ip=_client_ip(request), commit=True)
            raise sb.http_exception(exc) from exc
        if mapped is None or mapped.id != user.id:
            audit(db, actor_id=user.id, actor_role=user.role, action="reauth_failed",
                  object_type="auth", ip=_client_ip(request), commit=True)
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Re-authentication failed")
    else:
        if not verify_password(body.password, user.password_hash):
            audit(db, actor_id=user.id, actor_role=user.role, action="reauth_failed",
                  object_type="auth", ip=_client_ip(request), commit=True)
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Incorrect password")
    action_token = create_action_token(user.id, user.role)
    audit(db, actor_id=user.id, actor_role=user.role, action="action_token_issued",
          object_type="auth", ip=_client_ip(request), commit=True)
    return {"action_token": action_token,
            "expires_in_minutes": settings.jwt_action_ttl_minutes}


@router.post("/logout")
def logout(body: RefreshIn, db: Db, user: CurrentUser):
    if settings.supabase_enabled:
        h = sha256_hex(body.refresh_token)
        db.query(RefreshToken).filter(RefreshToken.token_hash == h).delete()
        # Revoke the Supabase session when we can reach Auth; log out is idempotent.
        try:
            session = sb.refresh_session(body.refresh_token)
            sb.sign_out(session.get("access_token", ""))
        except sb.SupabaseError:
            pass
        db.commit()
        audit(db, actor_id=user.id, actor_role=user.role, action="logout",
              object_type="auth", commit=True)
        return {"ok": True}
    h = sha256_hex(body.refresh_token)
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == h).first()
    if row:
        row.revoked = True
        db.commit()
    audit(db, actor_id=user.id, actor_role=user.role, action="logout",
          object_type="auth", commit=True)
    return {"ok": True}
