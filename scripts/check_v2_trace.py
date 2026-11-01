#!/usr/bin/env python3
"""Verify XML hierarchy, figure/table binding and sentence FTS in scipal_v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--term", default="diabetes")
    parser.add_argument("--source-type", default="xml", choices=("xml", "pdf"))
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    import psycopg

    dsn = args.pg_dsn
    if not dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")
    conn = psycopg.connect(dsn)
    rows = conn.execute(
        """
        SELECT p.paper_id,
               (SELECT count(*) FROM sentences s WHERE s.paper_id=p.paper_id) AS sentences,
               (SELECT count(*) FROM figures f WHERE f.paper_id=p.paper_id) AS figures,
               (SELECT count(*) FROM figures f WHERE f.paper_id=p.paper_id AND f.section_id IS NOT NULL) AS figures_bound,
               (SELECT count(*) FROM "tables" t WHERE t.paper_id=p.paper_id) AS tables,
               (SELECT count(*) FROM "tables" t WHERE t.paper_id=p.paper_id AND t.section_id IS NOT NULL) AS tables_bound
        FROM papers p
        WHERE EXISTS (
            SELECT 1 FROM sentences s
            JOIN paragraphs p2 ON p2.para_id=s.para_id
            WHERE s.paper_id=p.paper_id AND p2.section_id IS NOT NULL
              AND s.source_type=%s
        )
        ORDER BY p.paper_id
        LIMIT %s
        """,
        (args.source_type, args.limit),
    ).fetchall()
    report = []
    for paper_id, sentences, figures, figures_bound, tables, tables_bound in rows:
        trace = conn.execute(
            """
            SELECT s.sentence_id, sn.source_path, sec.section_id, sec.parent_id,
                   pa.paper_id, s.page, s.bbox
            FROM sentences s
            JOIN paragraphs p ON p.para_id=s.para_id
            JOIN sections sec ON sec.section_id=p.section_id
            JOIN papers pa ON pa.paper_id=s.paper_id
            JOIN source_nodes sn ON sn.node_id=s.source_node_id
            WHERE s.paper_id=%s AND p.section_id IS NOT NULL
              AND s.source_type=%s
            ORDER BY s.seq LIMIT 1
            """,
            (paper_id, args.source_type),
        ).fetchone()
        fts = conn.execute(
            """
            SELECT count(*) FROM sentences
            WHERE paper_id=%s AND source_type=%s
              AND search_vector @@ to_tsquery('english', %s)
            """,
            (paper_id, args.source_type, args.term),
        ).fetchone()[0]
        report.append(
            {
                "paper_id": paper_id,
                "sentences": sentences,
                "figures": figures,
                "figures_bound": figures_bound,
                "tables": tables,
                "tables_bound": tables_bound,
                "chain_sample": list(trace) if trace else None,
                "fts_hits": fts,
            }
        )
    conn.close()
    output = {
        "papers": len(report),
        "full_chain_papers": sum(1 for x in report if x["chain_sample"]),
        "figures_bound": sum(x["figures_bound"] for x in report),
        "figures_total": sum(x["figures"] for x in report),
        "tables_bound": sum(x["tables_bound"] for x in report),
        "tables_total": sum(x["tables"] for x in report),
        "fts_hits": sum(x["fts_hits"] for x in report),
        "items": report,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
