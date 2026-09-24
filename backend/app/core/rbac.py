"""Server-side authentication & authorization.

Role checks here run for every protected route; front-end route hiding is NOT
treated as authorization. Object-level helpers prevent IDOR/BOLA.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.core import supabase
from app.core.audit import audit
from app.core.security import TokenError, decode_token, TOKEN_ACCESS, TOKEN_ACTION
from app.db import get_db
from app.models.ops import OutdoorEvent
from app.models.registry import Project
from app.models.users import Organization, User

_bearer = HTTPBearer(auto_error=False)

Db = Annotated[Session, Depends(get_db)]


def _auth_failure(request: Request, actor: User | None, db: Session, reason: str):
    audit(
        db,
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action="authorization_failure",
        object_type="auth",
        detail={"reason": reason, "path": request.url.path},
        ip=request.client.host if request.client else None,
        commit=True,
    )


def get_current_user(
    request: Request,
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    """Resolve the authenticated user from our JWT or a Supabase access token."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    token = credentials.credentials
    payload: dict | None = None
    try:
        payload = decode_token(token, TOKEN_ACCESS)
    except TokenError:
        if not settings.supabase_enabled:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        try:
            payload = supabase.verify_access_token(token)
        except supabase.SupabaseError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user = None
    if settings.supabase_enabled and payload.get("sub") and "typ" not in payload:
        # Supabase JWT: map by uid first, then email.
        user = db.query(User).filter(User.supabase_uid == payload["sub"]).first()
        if user is None and payload.get("email"):
            user = db.query(User).filter(
                User.email == payload["email"].lower()).first()
    if user is None:
        try:
            user = db.get(User, int(payload["sub"]))
        except (TypeError, ValueError):
            user = None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """Route dependency: user must hold at least one of the given roles."""

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Role not permitted for this action")
        return user

    return checker


GovernmentUser = Annotated[User, Depends(require_roles("dosje", "state"))]
DosjeUser = Annotated[User, Depends(require_roles("dosje"))]
PmuUser = Annotated[User, Depends(require_roles("pmu"))]
NgoUser = Annotated[User, Depends(require_roles("ngo"))]


def sensitive_action(
    request: Request,
    db: Db,
    user: CurrentUser,
    x_action_token: Annotated[str | None, Header()] = None,
) -> User:
    """Re-authentication gate for highly sensitive operations.

    Requires a short-lived `action` token minted only after the user re-enters
    their password (POST /api/auth/confirm-password).
    """
    if not x_action_token:
        _auth_failure(request, user, db, "missing_action_token")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Re-authentication required")
    try:
        payload = decode_token(x_action_token, TOKEN_ACTION)
    except TokenError as exc:
        _auth_failure(request, user, db, "invalid_action_token")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Re-authentication token invalid") from exc
    if int(payload["sub"]) != user.id:
        _auth_failure(request, user, db, "action_token_user_mismatch")
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Re-authentication token mismatch")
    return user


SensitiveUser = Annotated[User, Depends(sensitive_action)]


# --- Object-level scope helpers -----------------------------------------------

def can_access_project(user: User, project: Project) -> bool:
    if user.role in ("dosje",):
        return True
    if user.role == "state":
        # Regional authority: only its own state.
        return bool(project.org.state_code and project.org.state_code == user.state_code)
    if user.role in ("pmu", "ngo"):
        return project.org_id == user.org_id
    return False


def can_access_outdoor_event(user: User, event: OutdoorEvent) -> bool:
    if user.role in ("dosje", "state"):
        return True
    if user.role == "ngo":
        return event.org_id == user.org_id
    if user.role == "pmu":
        return True  # PMU may verify spot-checks; enrolment scoped elsewhere
    return False


def scope_organizations(user: User, db: Session) -> list[int]:
    """Org ids the user may read (used to filter NGO/PMU queries)."""
    if user.role == "dosje":
        return [o.id for o in db.query(Organization).all()]
    if user.role == "state":
        return [o.id for o in db.query(Organization)
                .filter(Organization.state_code == user.state_code).all()]
    return [user.org_id] if user.org_id else []


def scope_projects(user: User, db: Session):
    """Project rows visible to the user (used to filter map/dashboard queries)."""
    query = db.query(Project)
    if user.role == "dosje":
        return query.all()
    if user.role == "state":
        return query.join(Organization).filter(Organization.state_code == user.state_code).all()
    if user.role in ("pmu", "ngo"):
        return query.filter(Project.org_id == user.org_id).all()
    return []
