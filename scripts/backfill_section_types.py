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
    parser.add_argument("--paper-id", action="append", required=True)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        for paper_id in args.paper_id:
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
                    "UPDATE paragraphs SET section_type=%s WHERE para_id=%s",
                    (label, para_id),
                )
            conn.commit()
            print(f"SECTION_TYPES_OK paper={paper_id} paragraphs={len(rows)} counts={counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
