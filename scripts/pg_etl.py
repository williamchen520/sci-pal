#!/usr/bin/env python3
"""P2 read-only ETL CLI.

Dry-run (default):
    python scripts/pg_etl.py --source backups/research_20261031_210616.db --checksum

Execute (requires PostgreSQL):
    $env:SCIPAL_PG_DSN="postgresql://..."
    python scripts/pg_etl.py --source backups/... --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db import DryRunWriter, PostgresCopyWriter, dry_run, run_etl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite snapshot (not data/research.db)")
    parser.add_argument("--tables", default="", help="comma-separated table names")
    parser.add_argument("--checksum", action="store_true", help="hash every row per table")
    parser.add_argument("--execute", action="store_true", help="COPY into PostgreSQL")
    parser.add_argument("--out", default="", help="write JSON report")
    args = parser.parse_args()

    tables = [item.strip() for item in args.tables.split(",") if item.strip()] or None
    if args.execute:
        dsn = os.environ.get("SCIPAL_PG_DSN") or ""
        if not dsn:
            print("SCIPAL_PG_DSN is required with --execute", file=sys.stderr)
            return 2
        report = run_etl(
            args.source,
            PostgresCopyWriter(dsn),
            tables=tables,
            checksum=args.checksum,
        )
    else:
        report = dry_run(args.source, tables=tables, checksum=args.checksum)

    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    failed = [item for item in report.tables if item.status != "ok"]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
