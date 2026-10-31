#!/usr/bin/env python3
"""Compare SQLite and PostgreSQL for the P5 paper-list canary."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.read_router import PAPER_COLUMNS, ReadRouter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--workspace", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    db = Path(args.db)
    workspace = args.workspace
    if not workspace:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT workspace_id FROM papers LIMIT 1").fetchone()
            workspace = row[0] if row else ""
        finally:
            conn.close()
    if not workspace:
        print("no workspace found", file=sys.stderr)
        return 2

    sqlite_rows = ReadRouter(db, canary_percent=0).list_papers(workspace).rows
    pg_rows = ReadRouter(db, pg_dsn=dsn, canary_percent=100).list_papers(workspace).rows
    sqlite_keys = [row[PAPER_COLUMNS[0]] for row in sqlite_rows]
    pg_keys = [row[PAPER_COLUMNS[0]] for row in pg_rows]
    field_diffs = sum(
        1 for left, right in zip(sqlite_rows, pg_rows) if left != right
    )
    report = {
        "db": str(db),
        "workspace": workspace,
        "sqlite_count": len(sqlite_rows),
        "postgres_count": len(pg_rows),
        "same_order": sqlite_keys == pg_keys,
        "field_diffs": field_diffs,
        "missing_in_pg": len(set(sqlite_keys) - set(pg_keys)),
        "extra_in_pg": len(set(pg_keys) - set(sqlite_keys)),
        "status": "ok" if sqlite_keys == pg_keys and field_diffs == 0 else "diff",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
