"""Minimal health endpoint — no version or technology disclosure."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"status": "ok", "time": __import__("datetime").datetime.now().astimezone().isoformat()}
