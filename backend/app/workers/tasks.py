"""Celery tasks (registered when the worker imports this module)."""
from __future__ import annotations

from app.db import SessionLocal
from app.models.cv import Camera
from app.workers.celery_app import celery_app


@celery_app.task(name="omniwatch.cctv.ingest_all")
def ingest_all_cameras() -> dict:
    from app.services.cv.engine import ingest_project_cameras
    db = SessionLocal()
    try:
        results = ingest_project_cameras(db)
        return {"processed": len(results),
                "alerts": sum(1 for r in results if r.get("alert"))}
    finally:
        db.close()


@celery_app.task(name="omniwatch.cctv.ingest_camera")
def ingest_camera(camera_id: int) -> dict:
    from app.services.cv.engine import ingest_once
    db = SessionLocal()
    try:
        camera = db.get(Camera, camera_id)
        if camera is None:
            return {"camera": camera_id, "error": "not_found"}
        return ingest_once(db, camera)
    finally:
        db.close()


@celery_app.task(name="omniwatch.reports.end_of_day")
def end_of_day_digest() -> dict:
    from datetime import date
    from app.services.reports import end_of_day
    db = SessionLocal()
    try:
        from app.models.ops import EodReport
        day = date.today()
        path, sha = end_of_day(db, actor_name="celery", report_date=day)
        db.add(EodReport(report_date=day, file_name=path.name, sha256=sha))
        db.commit()
        return {"file": path.name, "sha256": sha}
    finally:
        db.close()
