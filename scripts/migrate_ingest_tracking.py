#!/usr/bin/env python3
"""Apply the client ingest-tracking plugin schema.

Run this once with a migration/owner role before enabling
``SCIPAL_INGEST_TRACKING=1``. The application role intentionally has no DDL
privilege and must never create tables at startup.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "ingest_tracking"
    / "migrations"
    / "001_ingest_tracking.sql"
)


def migration_dsn() -> str:
    for key in ("SCIPAL_PG_MIGRATION_DSN", "SCIPAL_PG_OWNER_DSN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise SystemExit(
        "SCIPAL_PG_MIGRATION_DSN is required; "
        "the app runtime role cannot run DDL"
    )


def main() -> int:
    dsn = migration_dsn()
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.split(";") if part.strip()]
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            for statement in statements:
                conn.execute(statement)
    print(f"MIGRATION_OK {len(statements)} statements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
