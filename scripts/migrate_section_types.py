#!/usr/bin/env python3
"""Migrate paragraphs.section_type into the annotation table."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    parser.add_argument("--source", default="heuristic_v1")
    parser.add_argument("--version", default="2026-11-14")
    parser.add_argument("--clear-main", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(
            "SELECT para_id, section_type FROM paragraphs WHERE section_type IS NOT NULL"
        ).fetchall()
        for para_id, role in rows:
            conn.execute(
                """
                INSERT INTO paragraph_section_roles
                  (para_id, role, source, confidence, version)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (para_id, source) DO UPDATE SET
                  role=EXCLUDED.role,
                  confidence=EXCLUDED.confidence,
                  version=EXCLUDED.version,
                  updated_at=now()
                """,
                (para_id, role, args.source, 0.5, args.version),
            )
        if args.clear_main:
            conn.execute("UPDATE paragraphs SET section_type=NULL WHERE section_type IS NOT NULL")
        conn.commit()
        print(
            f"SECTION_ROLES_MIGRATED rows={len(rows)} source={args.source} "
            f"cleared_main={bool(args.clear_main)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
