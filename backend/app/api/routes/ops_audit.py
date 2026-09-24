"""Audit console + report endpoints (FR-15 audit reports)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.audit import audit
from app.core.rbac import Db, DosjeUser, SensitiveUser
from app.models.audit import AuditEvent
from app.models.ops import EodReport
from app.services.reports import end_of_day

router = APIRouter(tags=["ops-audit"])


@router.get("/api/audit")
def audit_log(db: Db, user: DosjeUser, action: str | None = None,
              object_type: str | None = None, limit: int = 200):
    q = db.query(AuditEvent).order_by(AuditEvent.ts.desc())
    if action:
        q = q.filter(AuditEvent.action == action)
    if object_type:
        q = q.filter(AuditEvent.object_type == object_type)
    rows = q.limit(min(limit, 1000)).all()
    return {"events": [{
        "id": e.id, "ts": e.ts.isoformat() if e.ts else None,
        "actor_id": e.actor_id, "actor_role": e.actor_role,
        "action": e.action, "object_type": e.object_type,
        "object_id": e.object_id, "ip": e.ip, "detail": e.detail,
    } for e in rows]}


class EodIn(BaseModel):
    report_date: date | None = None


@router.post("/api/reports/eod")
def generate_eod(body: EodIn, db: Db, user: SensitiveUser):
    """Generate the end-of-day digest PDF (also scheduled via Celery beat)."""
    if user.role != "dosje":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Officials only")
    day = body.report_date or date.today()
    path, sha = end_of_day(db, actor_name=user.full_name, report_date=day)
    row = EodReport(report_date=day, file_name=path.name, sha256=sha,
                    generated_by=user.id)
    db.add(row)
    db.commit()
    audit(db, actor_id=user.id, actor_role=user.role, action="eod_report_generated",
          object_type="report", object_id=path.name,
          detail={"sha256": sha, "date": day.isoformat()}, commit=True)
    return {"file": path.name, "sha256": sha, "date": day.isoformat()}


@router.get("/api/reports/eod")
def list_eod(db: Db, user: DosjeUser, limit: int = 30):
    rows = db.query(EodReport).order_by(EodReport.report_date.desc(),
                                        EodReport.id.desc()).limit(limit).all()
    return {"reports": [{
        "id": r.id, "date": r.report_date.isoformat(), "file": r.file_name,
        "sha256": r.sha256, "generated_by": r.generated_by,
        "created_at": r.created_at.isoformat(),
    } for r in rows]}


@router.get("/api/reports/eod/{report_id}/file")
def download_eod(report_id: int, db: Db, user: DosjeUser):
    row = db.get(EodReport, report_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found")
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "reports" / row.file_name
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report file missing")
    audit(db, actor_id=user.id, actor_role=user.role, action="report_downloaded",
          object_type="report", object_id=row.file_name, commit=True)
    return Response(content=path.read_bytes(), media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'inline; filename="{row.file_name}"',
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "no-store",
                        "X-Report-SHA256": row.sha256,
                    })
