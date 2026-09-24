"""Database engine/session helpers.

Runs against PostgreSQL (PostGIS image) in the Docker composition and against
SQLite for local development/tests. Domain logic (geofence distance checks,
risk math) is deliberately DB-agnostic and lives in app/core / app/services.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _build_engine(url: str):
    if url.startswith("sqlite"):
        # Ensure parent dir exists for file-based sqlite DBs.
        path = url.split("///")[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


engine = _build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(admin_url: str | None = None) -> None:
    """Create tables. The one-shot migrate container passes the admin URL."""
    global engine, SessionLocal  # noqa: PLW0603
    target = admin_url or settings.database_url
    if admin_url and admin_url != settings.database_url:
        eng = _build_engine(admin_url)
        Base.metadata.create_all(eng)
        eng.dispose()
        return
    Base.metadata.create_all(engine)
