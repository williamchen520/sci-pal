#!/usr/bin/env python3
"""Remove tenancy tables from SQLite outbox replication.

Tenancy is PG-primary. Keeping dualwrite triggers would let SQLite mirror writes
queue redundant PG upserts; this script drops those triggers and clears pending
outbox rows for the affected tables. Processed history is left intact.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

TABLES = ("users", "workspaces", "memberships")


def remove(db: Path, *, dry_run: bool = False) -> dict:
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
        pending = 0
        if "dual_write_outbox" in {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            placeholders = ",".join("?" * len(TABLES))
            pending = conn.execute(
                f"SELECT count(*) FROM dual_write_outbox "
                f"WHERE processed_at IS NULL AND table_name IN ({placeholders})",
                TABLES,
            ).fetchone()[0]
        if not dry_run:
            for name in to_drop:
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            if pending:
                placeholders = ",".join("?" * len(TABLES))
                conn.execute(
                    f"DELETE FROM dual_write_outbox "
                    f"WHERE processed_at IS NULL AND table_name IN ({placeholders})",
                    TABLES,
                )
            conn.commit()
        remaining = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_%'"
            )
        }
        return {
            "db": str(db),
            "dry_run": dry_run,
            "dropped": to_drop,
            "pending_tenancy_rows": pending,
            "remaining_tenancy_triggers": sorted(
                name for name in remaining if any(name.startswith(f"dualwrite_{t}_") for t in TABLES)
            ),
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = remove(Path(args.db), dry_run=args.dry_run)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if report["remaining_tenancy_triggers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
