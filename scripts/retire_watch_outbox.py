#!/usr/bin/env python3
"""Retire watch tables from the SQLite outbox.

Watch writes are PG-first; the outbox is no longer the repair path for these
tables. Processed history is kept, pending watch rows are removed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

TABLES = ("watch_profiles", "watch_items", "watch_runs", "watch_seen")


def retire(db: Path, *, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(f"file:{db}", uri=True, timeout=30)
    try:
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_%'"
            )
        }
        to_drop = [
            f"dualwrite_{table}_{suffix}"
            for table in TABLES
            for suffix in ("ai", "au", "ad")
            if f"dualwrite_{table}_{suffix}" in existing
        ]
        pending = conn.execute(
            "SELECT count(*) FROM dual_write_outbox "
            "WHERE processed_at IS NULL AND table_name IN (?,?,?,?)",
            TABLES,
        ).fetchone()[0]
        if not dry_run:
            for trigger in to_drop:
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            conn.execute(
                "DELETE FROM dual_write_outbox "
                "WHERE processed_at IS NULL AND table_name IN (?,?,?,?)",
                TABLES,
            )
            conn.commit()
        remaining = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_%'"
            )
            if any(row[0].startswith(f"dualwrite_{t}_") for t in TABLES)
        ]
        return {
            "db": str(db),
            "dry_run": dry_run,
            "dropped": to_drop,
            "pending_removed": pending,
            "remaining_watch_triggers": sorted(remaining),
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = retire(Path(args.db), dry_run=args.dry_run)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if report["remaining_watch_triggers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
