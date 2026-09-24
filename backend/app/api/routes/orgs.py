"""Organisations reference (registry dropdowns, DoSJE/state only)."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.rbac import Db, GovernmentUser
from app.models.users import Organization

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("")
def list_organizations(db: Db, user: GovernmentUser):
    rows = db.query(Organization).order_by(Organization.name).all()
    return [{"id": o.id, "name": o.name, "kind": o.kind,
             "state_code": o.state_code} for o in rows]
