#!/usr/bin/env python3
"""Create scipal_core and apply the business-only schema.

This is intentionally separate from scipal_rebuild. It never creates or
touches papers/paragraphs/sentences/paragraph_embeddings.

Usage:
    SCIPAL_CORE_DSN=postgresql://.../scipal_core \
    SCIPAL_PG_ADMIN_DSN=postgresql://.../scipal_bench \
    python scripts/init_core_db.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "deploy" / "sql" / "scipal_core_schema.sql"


def _dbname(dsn: str) -> str:
    from psycopg.conninfo import conninfo_to_dict

    return conninfo_to_dict(dsn)["dbname"]


def main() -> int:
    core_dsn = os.environ.get("SCIPAL_CORE_DSN", "").strip()
    admin_dsn = os.environ.get("SCIPAL_PG_ADMIN_DSN", "").strip()
    if not core_dsn:
        raise SystemExit("SCIPAL_CORE_DSN is required")
    if not admin_dsn:
        raise SystemExit("SCIPAL_PG_ADMIN_DSN is required")
    if not SCHEMA.exists():
        raise SystemExit(f"schema file not found: {SCHEMA}")

    dbname = _dbname(core_dsn)
    admin_dsn = admin_dsn.replace(f"/{_dbname(admin_dsn)}", "/postgres")
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        exists = admin.execute(
            "select 1 from pg_database where datname = %s", (dbname,)
        ).fetchone()
        if not exists:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
            print(f"created database {dbname}")
        else:
            print(f"database {dbname} already exists")

    psql = os.environ.get("PSQL_BIN", "psql")
    try:
        subprocess.run(
            [psql, core_dsn, "-v", "ON_ERROR_STOP=1", "-f", str(SCHEMA)],
            check=True,
        )
    except FileNotFoundError:
        print("psql not found; using psycopg multi-statement fallback", file=sys.stderr)
        with psycopg.connect(core_dsn, autocommit=True) as conn:
            conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("scipal_core schema applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
