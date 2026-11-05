"""G3.8 gate: refuse to retire the SQLite outbox unless PG is in sync."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

from services.db.dual_write import DEFAULT_TABLES, OUTBOX
from services.db.etl import quote_ident


def collect(sqlite_path: str, pg_dsn: str) -> dict:
    import psycopg

    sqlite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    pg = psycopg.connect(pg_dsn)
    try:
        pending = sqlite.execute(
            f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL"
        ).fetchone()[0]
        tables = {}
        for table in DEFAULT_TABLES:
            try:
                sqlite_count = sqlite.execute(
                    f"SELECT COUNT(*) FROM {quote_ident(table)}"
                ).fetchone()[0]
            except sqlite3.Error:
                sqlite_count = None
            try:
                pg_count = pg.execute(
                    f"SELECT COUNT(*) FROM {quote_ident(table)}"
                ).fetchone()[0]
            except Exception:  # noqa: BLE001
                pg_count = None
            tables[table] = {
                "sqlite": sqlite_count,
                "pg": pg_count,
                "ok": sqlite_count == pg_count and sqlite_count is not None,
            }
        return {
            "outbox_pending": pending,
            "tables": tables,
            "ok": pending == 0 and all(row["ok"] for row in tables.values()),
        }
    finally:
        sqlite.close()
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--pg-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    args = parser.parse_args()
    if not args.pg_dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    report = collect(args.sqlite, args.pg_dsn)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
