#!/usr/bin/env python3
"""Compare production SQLite tenancy mirror with PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TABLES = {
    "users": {
        "key": ("user_id",),
        "columns": ("user_id", "username", "email", "display_name", "password_hash", "status", "is_admin"),
    },
    "workspaces": {
        "key": ("workspace_id",),
        "columns": ("workspace_id", "name", "owner_user_id"),
    },
    "memberships": {
        "key": ("workspace_id", "user_id"),
        "columns": ("workspace_id", "user_id", "role", "status"),
    },
}


def normalize(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def row_map(rows, columns, key):
    result = {}
    for row in rows:
        item = {column: normalize(row[column]) for column in columns}
        result[tuple(item[column] for column in key)] = item
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from psycopg import connect
    from psycopg.rows import dict_row

    if not args.pg_dsn:
        raise SystemExit("SCIPAL_PG_DSN is required")

    sq = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row
    report = {"db": args.db, "tables": {}, "drift": False}
    try:
        with connect(args.pg_dsn, row_factory=dict_row) as pg:
            for table, spec in TABLES.items():
                columns = spec["columns"]
                key = spec["key"]
                col_sql = ", ".join(f'"{c}"' for c in columns)
                sqlite_rows = row_map(sq.execute(f'SELECT {col_sql} FROM "{table}"').fetchall(), columns, key)
                pg_rows = row_map(pg.execute(f'SELECT {col_sql} FROM "{table}"').fetchall(), columns, key)
                only_sqlite = sorted(set(sqlite_rows) - set(pg_rows))
                only_pg = sorted(set(pg_rows) - set(sqlite_rows))
                changed = []
                for k in sorted(set(sqlite_rows) & set(pg_rows)):
                    if sqlite_rows[k] != pg_rows[k]:
                        changed.append(
                            {
                                "key": dict(zip(key, k)),
                                "sqlite": sqlite_rows[k],
                                "pg": pg_rows[k],
                            }
                        )
                table_report = {
                    "sqlite_count": len(sqlite_rows),
                    "pg_count": len(pg_rows),
                    "only_sqlite": [dict(zip(key, k)) for k in only_sqlite[:20]],
                    "only_pg": [dict(zip(key, k)) for k in only_pg[:20]],
                    "changed": changed[:20],
                    "drift": bool(only_sqlite or only_pg or changed),
                }
                report["tables"][table] = table_report
                report["drift"] = report["drift"] or table_report["drift"]
    finally:
        sq.close()

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not report["drift"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
