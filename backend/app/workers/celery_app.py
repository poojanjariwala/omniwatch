"""Celery wiring for asynchronous CCTV ingestion + end-of-day digest.

In broker-less demo mode the API calls the same service functions directly, so
heavy AI work is still encapsulated behind app/services/cv/engine.ingest_once.
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "omniwatch",
    broker=settings.broker_url,
    backend=settings.result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_max_tasks_per_child=200,
)

celery_app.conf.beat_schedule = {
    "cctv-ingest-every-30s": {
        "task": "omniwatch.cctv.ingest_all",
        "schedule": settings.celery_ingest_seconds,
    },
    "end-of-day-digest-daily": {
        "task": "omniwatch.reports.end_of_day",
        "schedule": crontab(hour=23, minute=55),
    },
}
