"""Schema bootstrap used by the migrate one-shot container.

Runs with the privileged admin account so the application account can hold
DML-only privileges (least privilege).
"""
from __future__ import annotations

import os

from sqlalchemy import text

import app.models  # noqa: F401  -- imports every model so Base.metadata is populated
from app.db import init_db


def main() -> None:
    admin_url = os.environ.get("OMNIWATCH_DB_ADMIN_URL") or ""
    init_db(admin_url=admin_url or None)
    if admin_url:
        from sqlalchemy import create_engine
        role = os.environ.get("OMNIWATCH_APP_DB_ROLE", "omniwatch_app")
        engine = create_engine(admin_url)
        with engine.begin() as conn:
            conn.execute(text(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
            ))
            conn.execute(text(
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}"
            ))
        engine.dispose()
    print("Schema ready.")  # noqa: T201


if __name__ == "__main__":
    main()
