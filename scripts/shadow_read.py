#!/usr/bin/env python3
"""P3 shadow read CLI (read-only).

Example:
    $env:SCIPAL_PG_DSN="postgresql://..."
    python scripts/shadow_read.py --source backups/research_...db \
      --tables papers:paper_id,paragraphs:para_id,sentences:sentence_id \
      --fts-query "hepatocellular carcinoma" --out docs/PostgreSQL迁移-P3-shadow.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.shadow_read import ShadowReader, write_report  # noqa: E402

DEFAULT_TABLES = [
    ("papers", "paper_id"),
    ("paragraphs", "para_id"),
    ("sentences", "sentence_id"),
    ("claim_cards", "claim_id"),
    ("claim_card_evidence", "evidence_id"),
    ("watch_items", "id"),
    ("users", "user_id"),
    ("workspaces", "workspace_id"),
]


def parse_tables(value: str):
    if not value:
        return DEFAULT_TABLES
    out = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise SystemExit(f"table must be name:key, got {item!r}")
        table, key = item.split(":", 1)
        out.append((table.strip(), key.strip()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite snapshot (not data/research.db)")
    parser.add_argument("--tables", default="", help="comma-separated table:key list")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--fts-query", action="append", default=[])
    parser.add_argument("--fts-limit", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("psycopg is required; install psycopg[binary]", file=sys.stderr)
        return 2

    pg = psycopg.connect(dsn)
    try:
        reader = ShadowReader(args.source, pg)
        report = reader.run(
            parse_tables(args.tables),
            limit=args.limit,
            fts_queries=args.fts_query,
            fts_limit=args.fts_limit,
        )
    finally:
        pg.close()

    text = __import__("json").dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        write_report(report, args.out)
    print(text)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
