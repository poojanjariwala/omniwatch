"""Short unique code generators for inspections, alerts, cases, distributions."""
from __future__ import annotations

import base64
import time

from app.core.randomization import random_hex


def _stamp() -> str:
    return base64.b32encode(int(time.time() * 1000).to_bytes(6, "big")).decode().rstrip("=").lower()


def gen_code(prefix: str, kind: str = "") -> str:
    parts = [prefix]
    if kind:
        parts.append(kind.upper())
    parts.append(f"{_stamp()}{random_hex(3)}")
    return "-".join(parts)[:60]


def gen_inspection_code(kind: str) -> str:
    return gen_code("OWI", kind)


def gen_alert_code(kind: str) -> str:
    return gen_code("OWA", kind)


def gen_case_code() -> str:
    return gen_code("OWC")


def gen_distribution_code() -> str:
    return gen_code("OWD")


def gen_event_code() -> str:
    return gen_code("OWE")
