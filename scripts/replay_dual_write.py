#!/usr/bin/env python3
"""Replay P4 metadata outbox rows into PostgreSQL.

SQLite remains the primary database. Run this from cron/systemd, or use
``--loop`` for a long-running worker.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import DB_PATH  # noqa: E402
from services.db.dual_write import replay  # noqa: E402


def run_once(db: Path, limit: int) -> dict:
    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        raise SystemExit("SCIPAL_PG_DSN is required")
    try:
        import psycopg
    except ImportError as exc:
        raise SystemExit("psycopg is required") from exc
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    pg = psycopg.connect(dsn)
    try:
        return replay(conn, pg, limit=limit)
    finally:
        pg.close()
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=float, default=10.0)
    args = parser.parse_args()
    db = Path(args.db)

    while True:
        report = run_once(db, args.limit)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if not args.loop:
            return 0 if report["failed"] == 0 else 1
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
