#!/usr/bin/env python3
"""Persist heuristic section_type onto paragraphs for selected papers."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.reader import _section_bounds, _section_type


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        paper_ids = args.paper_id
        if not paper_ids:
            paper_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT p.paper_id FROM papers p "
                    "WHERE EXISTS (SELECT 1 FROM paragraphs x WHERE x.paper_id=p.paper_id) "
                    "AND NOT EXISTS (SELECT 1 FROM paragraphs x WHERE x.paper_id=p.paper_id AND x.section_type IS NOT NULL) "
                    "ORDER BY p.created_at DESC LIMIT %s",
                    (max(1, args.limit),),
                ).fetchall()
            ]
        for paper_id in paper_ids:
            bounds = _section_bounds(paper_id)
            rows = conn.execute(
                "SELECT para_id, sequence, section_level1, section_level2 "
                "FROM paragraphs WHERE paper_id=%s ORDER BY sequence",
                (paper_id,),
            ).fetchall()
            counts: dict[str, int] = {}
            for para_id, sequence, level1, level2 in rows:
                label = _section_type(
                    {
                        "first_sequence": sequence,
                        "section_level1": level1,
                        "section_level2": level2,
                    },
                    bounds,
                )
                counts[label] = counts.get(label, 0) + 1
                conn.execute(
                    """
                    INSERT INTO paragraph_section_roles
                      (para_id, role, source, confidence, version)
                    VALUES (%s,%s,'heuristic_v1',0.5,'2026-11-14')
                    ON CONFLICT (para_id, source) DO UPDATE SET
                      role=EXCLUDED.role,
                      confidence=EXCLUDED.confidence,
                      version=EXCLUDED.version,
                      updated_at=now()
                    """,
                    (para_id, label),
                )
            conn.commit()
            print(f"SECTION_TYPES_OK paper={paper_id} paragraphs={len(rows)} counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
