#!/usr/bin/env python3
"""Read-only schema parity report: SQLite research.db vs PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _sqlite_tables(conn: sqlite3.Connection) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        if "_fts_" in name:
            continue
        out[name] = {row[1] for row in conn.execute(f'PRAGMA table_info("{name}")')}
    return out


def _pg_tables(dsn: str) -> dict[str, set[str]]:
    import psycopg

    with psycopg.connect(dsn) as pg:
        rows = pg.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' ORDER BY table_name, ordinal_position"
        ).fetchall()
    out: dict[str, set[str]] = {}
    for table, column in rows:
        out.setdefault(table, set()).add(column)
    return out


def compare(sqlite_path: Path, dsn: str) -> dict:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        sqlite = _sqlite_tables(conn)
    finally:
        conn.close()
    pg = _pg_tables(dsn)
    common = sorted(set(sqlite) & set(pg))
    column_diffs = {}
    for table in common:
        missing_in_pg = sorted(sqlite[table] - pg[table])
        missing_in_sqlite = sorted(pg[table] - sqlite[table])
        if missing_in_pg or missing_in_sqlite:
            column_diffs[table] = {
                "missing_in_pg": missing_in_pg,
                "missing_in_sqlite": missing_in_sqlite,
            }
    return {
        "sqlite_tables": len(sqlite),
        "pg_tables": len(pg),
        "common_tables": len(common),
        "sqlite_only": sorted(set(sqlite) - set(pg)),
        "pg_only": sorted(set(pg) - set(sqlite)),
        "column_diffs": column_diffs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = compare(Path(args.sqlite), args.pg_dsn)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
