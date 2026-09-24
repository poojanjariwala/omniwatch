"""Seed SAMPLE/DEMO data for OmniWatch.

Run from repo root:
    python scripts/seed_demo.py
or from backend/:
    python -m app.bootstrap_entry

The bootstrap never touches real data and never runs in production mode.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.bootstrap import ensure_seed_data  # noqa: E402


def main() -> None:
    ensure_seed_data()
    print("SAMPLE/DEMO data seeded. Logins:")  # noqa: T201
    print("  dosje   admin@omniwatch.demo.in / Admin@Demo123")  # noqa: T201
    print("  pmu     rakesh@pmu.demo.in / Pmu@Demo123")  # noqa: T201
    print("  ngo     ngo@demo.org / Ngo@Demo123")  # noqa: T201
    print("  ngo2    ngo2@demo.org / Ngo2@Demo123")  # noqa: T201
    print("  state   state@omniwatch.demo.in / State@Demo123")  # noqa: T201
    print("  ben     ben@demo.in / Ben@Demo123")  # noqa: T201


if __name__ == "__main__":
    main()
