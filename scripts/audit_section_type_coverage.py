#!/usr/bin/env python3
"""Report section_type coverage over the corpus."""

from __future__ import annotations

import argparse
import json
import os

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_CORPUS_DSN", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_CORPUS_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        total_papers = conn.execute(
            "SELECT count(*) FROM papers p WHERE EXISTS "
            "(SELECT 1 FROM paragraphs x WHERE x.paper_id=p.paper_id)"
        ).fetchone()[0]
        classified_papers = conn.execute(
            "SELECT count(DISTINCT paper_id) FROM paragraphs WHERE section_type IS NOT NULL"
        ).fetchone()[0]
        total_paragraphs = conn.execute(
            "SELECT count(*) FROM paragraphs WHERE paper_id IN "
            "(SELECT paper_id FROM papers)"
        ).fetchone()[0]
        classified_paragraphs = conn.execute(
            "SELECT count(*) FROM paragraphs WHERE section_type IS NOT NULL"
        ).fetchone()[0]
        by_type = dict(
            conn.execute(
                "SELECT section_type, count(*) FROM paragraphs "
                "WHERE section_type IS NOT NULL GROUP BY section_type ORDER BY count(*) DESC"
            ).fetchall()
        )
    result = {
        "total_papers": int(total_papers),
        "classified_papers": int(classified_papers),
        "pending_papers": int(total_papers) - int(classified_papers),
        "total_paragraphs": int(total_paragraphs),
        "classified_paragraphs": int(classified_paragraphs),
        "pending_paragraphs": int(total_paragraphs) - int(classified_paragraphs),
        "by_type": {str(k): int(v) for k, v in by_type.items()},
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"SECTION_COVERAGE papers={result['classified_papers']}/{result['total_papers']} "
            f"paragraphs={result['classified_paragraphs']}/{result['total_paragraphs']}"
        )
        for key, value in result["by_type"].items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
