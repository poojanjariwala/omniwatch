"""QR lifecycle (FR-12): batch issue (NGO/gov), atomic scan, logs (scenario B)."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.limits import QR_SCAN_LIMIT, limiter
from app.core.rbac import Db, require_roles
from app.models.ops import Distribution, Project, QrCode, QrScanLog
from app.models.users import Organization, User
from app.schemas.serializers import (
    distribution_public, qr_code_public, scan_log_public,
)
from app.services.qr import distribution_stats, issue_batch, scan_code

router = APIRouter(prefix="/api/qr", tags=["qr"])

GovOrNgo = Annotated[User, Depends(require_roles("ngo", "dosje", "state"))]
Scanner = Annotated[User, Depends(require_roles("ngo", "dosje", "pmu", "state"))]
VerifyUser = Annotated[User, Depends(require_roles("ngo", "beneficiary", "dosje",
                                                   "pmu", "state"))]


class BatchIn(BaseModel):
    project_id: int
    title: str = Field(min_length=2, max_length=200)
    count: int = Field(ge=1, le=5000)
    distribution_date: date | None = None


class ScanIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    lat: float | None = None
    lng: float | None = None
    recipient_token: str | None = Field(default=None, max_length=120)


class VerifyIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)


def _user_project(db, project_id: int, user) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    if user.role == "ngo":
        if project.org_id != user.org_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                detail="Not your organisation's project")
    elif user.role == "state":
        org = db.get(Organization, project.org_id)
        if org is None or org.state_code != user.state_code:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _user_dist_rows(db, user):
    q = db.query(Distribution).order_by(Distribution.created_at.desc())
    if user.role == "ngo":
        q = q.filter(Distribution.org_id == user.org_id)
    elif user.role == "state":
        org_ids = [o.id for o in db.query(Organization)
                   .filter(Organization.state_code == user.state_code).all()]
        q = q.filter(Distribution.org_id.in_(org_ids) if org_ids else [-1])
    return q.all()


def _distribution_or_404(db, distribution_id: int, user) -> Distribution:
    dist = db.get(Distribution, distribution_id)
    if dist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    if user.role == "ngo" and dist.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    if user.role == "state":
        org = db.get(Organization, dist.org_id)
        if org is None or org.state_code != user.state_code:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Distribution not found")
    return dist


@router.post("/batches")
def create_batch(body: BatchIn, db: Db, user: GovOrNgo):
    project = _user_project(db, body.project_id, user)
    try:
        dist = issue_batch(db, project=project, org_id=project.org_id, actor=user,
                           title=body.title, count=body.count,
                           distribution_date=body.distribution_date)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    stats = distribution_stats(db, dist.id)
    codes = db.query(QrCode).filter(QrCode.distribution_id == dist.id).limit(100).all()
    return {"distribution": distribution_public(dist, **stats, project_name=project.name),
            "sample_codes": [qr_code_public(c) for c in codes]}


@router.get("/distributions")
def list_distributions(db: Db, user: GovOrNgo):
    rows = _user_dist_rows(db, user)
    orgs = {o.id: o.name for o in db.query(Organization).all()}
    out = []
    for d in rows:
        stats = distribution_stats(db, d.id)
        p = db.get(Project, d.project_id) if d.project_id else None
        out.append(distribution_public(d, **stats,
                                       project_name=p.name if p else None,
                                       org_name=orgs.get(d.org_id)))
    return {"distributions": out}


@router.get("/distributions/{distribution_id}/codes")
def distribution_codes(distribution_id: int, db: Db, user: GovOrNgo):
    dist = _distribution_or_404(db, distribution_id, user)
    codes = db.query(QrCode).filter(QrCode.distribution_id == dist.id) \
        .order_by(QrCode.serial).all()
    return {"codes": [qr_code_public(c) for c in codes]}


@router.post("/scan")
@limiter.limit(QR_SCAN_LIMIT)
def scan(request: Request, body: ScanIn, db: Db, user: Scanner):
    """Validate + consume a code atomically. Duplicates/replays are blocked."""
    return scan_code(db, actor=user, code_str=body.code, lat=body.lat,
                     lng=body.lng, recipient_token=body.recipient_token)


@router.get("/scan-logs")
def scan_logs(db: Db, user: GovOrNgo,
              distribution_id: int | None = Query(default=None),
              ok: bool | None = None, limit: int = Query(default=100, ge=1, le=500)):
    dists = _user_dist_rows(db, user)
    ids = {d.id for d in dists}
    code_query = db.query(QrCode)
    if distribution_id:
        dist = _distribution_or_404(db, distribution_id, user)
        code_ids = [c.id for c in code_query.filter(
            QrCode.distribution_id == dist.id).all()]
    elif ids:
        code_ids = [c.id for c in code_query
                    .filter(QrCode.distribution_id.in_(ids)).all()]
    else:
        code_ids = []
    q = db.query(QrScanLog).order_by(QrScanLog.created_at.desc())
    q = q.filter(QrScanLog.code_id.in_(code_ids) if code_ids else QrScanLog.id < 0)
    if ok is not None:
        q = q.filter(QrScanLog.ok == ok)
    logs = q.limit(limit).all()
    code_map = {c.id: c for c in db.query(QrCode).filter(
        QrCode.id.in_([l.code_id for l in logs] or [-1])).all()}
    actors = {u.id: u.full_name for u in db.query(User).filter(
        User.id.in_([l.scanned_by for l in logs if l.scanned_by] or [-1])).all()}
    return {"logs": [scan_log_public(l,
                                     code_code=code_map[l.code_id].code if l.code_id in code_map else None,
                                     actor_name=actors.get(l.scanned_by)) for l in logs]}


@router.post("/verify")
def verify_code(body: VerifyIn, db: Db, user: VerifyUser):
    """Read-only status check — reveals no personal, alert or risk data."""
    code = db.query(QrCode).filter(QrCode.code == body.code).first()
    if code is None:
        return {"status": "not_found", "message": "Code not recognised"}
    return {"status": code.status,
            "message": ("Item already handed out" if code.status == "consumed"
                        else "Item available"),
            "serial": code.serial}
