#!/usr/bin/env python3
"""P4 dual-write health check.

Read-only: reports outbox lag, failed rows, trigger count, and per-table row
counts between SQLite and PostgreSQL. Exit non-zero on a threshold breach.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import DB_PATH  # noqa: E402
from services.db.dual_write import DEFAULT_TABLES, OUTBOX, discover_tables  # noqa: E402
from services.db.etl import quote_ident  # noqa: E402


def collect(conn: sqlite3.Connection, pg, tables=None) -> dict:
    names = list(tables or DEFAULT_TABLES)
    specs = discover_tables(conn, names)
    counts = []
    for spec in specs:
        sqlite_count = conn.execute(
            f"SELECT COUNT(*) FROM {quote_ident(spec.name)}"
        ).fetchone()[0]
        row = pg.execute(f"SELECT COUNT(*) FROM {quote_ident(spec.name)}").fetchone()
        pg_count = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        counts.append(
            {
                "table": spec.name,
                "sqlite": sqlite_count,
                "postgres": pg_count,
                "match": sqlite_count == pg_count,
            }
        )
    pending = conn.execute(
        f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    failed = conn.execute(
        f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL AND last_error IS NOT NULL"
    ).fetchone()[0]
    oldest = conn.execute(
        f"SELECT MIN(created_at) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    age = conn.execute(
        f"SELECT (julianday('now') - julianday(MIN(created_at))) * 86400 "
        f"FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    triggers = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_%'"
    ).fetchone()[0]
    return {
        "pending": pending,
        "failed": failed,
        "oldest_pending": oldest,
        "pending_age_seconds": round(age, 1) if age is not None else None,
        "triggers": triggers,
        "tables": counts,
        "mismatches": [c["table"] for c in counts if not c["match"]],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--max-pending", type=int, default=100)
    parser.add_argument("--max-age", type=float, default=300.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("psycopg is required", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pg = psycopg.connect(dsn)
    try:
        report = collect(conn, pg)
    finally:
        pg.close()
        conn.close()

    bad = (
        report["failed"] > 0
        or report["pending"] > args.max_pending
        or (report["pending_age_seconds"] or 0) > args.max_age
        or bool(report["mismatches"])
    )
    report["status"] = "degraded" if bad else "ok"
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
