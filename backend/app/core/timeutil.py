"""Datetime helpers: SQLite stores naive datetimes even for timezone-aware
columns, so anything read back from the DB must be normalised before it is
compared against freshly-created aware datetimes (utcnow etc.)."""
from __future__ import annotations

from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_iso_utc(value: str) -> datetime:
    """Parse a client-supplied ISO-8601 timestamp into an aware UTC datetime.

    Python < 3.11's fromisoformat() rejects the 'Z' suffix that JS
    Date.toISOString() emits, so normalise it before parsing. Raises
    ValueError on malformed input (routes map that to HTTP 422).
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    return as_utc(datetime.fromisoformat(text))


def utc_naive_iso(value: datetime | None) -> str | None:
    """Stable ISO string in UTC without an offset suffix.

    SQLite returns naive datetimes even for tz-aware columns, so canonical
    strings (used inside hash chain metadata) must not depend on the driver's
    tz behaviour.
    """
    if value is None:
        return None
    utc = as_utc(value)
    return utc.replace(tzinfo=None).isoformat()
