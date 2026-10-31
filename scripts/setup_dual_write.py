#!/usr/bin/env python3
"""Install P4 metadata dual-write triggers on a SQLite database.

This modifies the target database's schema and adds an outbox. It always
creates a timestamped backup first. FTS tables are intentionally excluded.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import DB_PATH  # noqa: E402
from scripts.backup_sqlite import create_backup  # noqa: E402
from services.db.dual_write import DEFAULT_TABLES, install  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--tables", default="", help="comma-separated table names")
    parser.add_argument("--apply", action="store_true", help="actually modify the database")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    db = Path(args.db)
    names = [x.strip() for x in args.tables.split(",") if x.strip()] or list(DEFAULT_TABLES)
    if not args.apply:
        print(json.dumps({"db": str(db), "tables": names, "applied": False}, indent=2))
        return 0

    backup = create_backup(db, db.parent / "backups")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        report = install(conn, names)
        report["backup"] = backup["dest"]
        report["db"] = str(db)
        report["integrity"] = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["integrity"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
