#!/usr/bin/env python3
"""Profile sentence FTS query variants (terms, ranker, candidate depth)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.fts_query_builder import _extract_keywords  # noqa: E402


def sql_for(ranker: str) -> str:
    expression = "ts_rank" if ranker == "rank" else "ts_rank_cd"
    return f"""
        WITH q AS (SELECT to_tsquery('english', %s) AS query)
        SELECT s.sentence_id, s.paper_id, s.para_id, s.section_id, s.text,
               s.source_type, s.page, s.bbox, sn.source_path, p.title,
               {expression}(s.search_vector, q.query) AS rank
        FROM sentences s
        JOIN papers p ON p.paper_id = s.paper_id
        LEFT JOIN source_nodes sn ON sn.node_id = s.source_node_id
        CROSS JOIN q
        WHERE s.search_vector @@ q.query
        ORDER BY rank DESC, s.sentence_id
        LIMIT %s
    """


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--query", default="What is ICI rechallenge in hepatocellular carcinoma?")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    import psycopg
    from psycopg.rows import dict_row

    terms = _extract_keywords(args.query)
    variants = []
    for term_count in (5, 8, 12):
        for top_k in (200, 500, 1000):
            for ranker in ("rank", "rank_cd"):
                variants.append((term_count, top_k, ranker))
    results = []
    with psycopg.connect(args.pg_dsn, row_factory=dict_row) as conn:
        for term_count, top_k, ranker in variants:
            ts_query = " | ".join(terms[:term_count])
            started = time.perf_counter()
            rows = conn.execute(sql_for(ranker), (ts_query, top_k)).fetchall()
            elapsed = time.perf_counter() - started
            results.append(
                {
                    "terms": term_count,
                    "top_k": top_k,
                    "ranker": ranker,
                    "elapsed": round(elapsed, 4),
                    "rows": len(rows),
                }
            )
            print(
                f"terms={term_count} top_k={top_k} ranker={ranker} "
                f"elapsed={elapsed:.3f}s rows={len(rows)}",
                file=sys.stderr,
                flush=True,
            )
    output = {"query": args.query, "results": results}
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
