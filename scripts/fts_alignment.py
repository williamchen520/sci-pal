#!/usr/bin/env python3
"""FTS tokenizer/stemmer alignment experiment (read-only).

Compares:
  SQLite unicode61 (current) vs PostgreSQL english
  SQLite porter             vs PostgreSQL english
  SQLite unicode61          vs PostgreSQL simple
  SQLite porter             vs PostgreSQL simple

Builds a temporary SQLite FTS table with the porter tokenizer; does not modify
the source database or the PostgreSQL schema.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.etl import assert_snapshot  # noqa: E402

DEFAULT_QUERIES = [
    "hepatocellular carcinoma",
    "immune checkpoint inhibitor",
    "tumor microenvironment",
]


def sqlite_matches(conn, query, limit):
    top = [
        row[0]
        for row in conn.execute(
            "SELECT para_id FROM paragraphs_fts WHERE paragraphs_fts MATCH ? "
            "ORDER BY bm25(paragraphs_fts) LIMIT ?",
            (query, limit),
        ).fetchall()
    ]
    all_ids = {
        row[0]
        for row in conn.execute(
            "SELECT para_id FROM paragraphs_fts WHERE paragraphs_fts MATCH ?",
            (query,),
        ).fetchall()
    }
    return top, all_ids


def sqlite_porter_matches(conn, query, limit):
    top = [
        row[0]
        for row in conn.execute(
            "SELECT para_id FROM paragraphs_fts_porter WHERE paragraphs_fts_porter MATCH ? "
            "ORDER BY bm25(paragraphs_fts_porter) LIMIT ?",
            (query, limit),
        ).fetchall()
    ]
    all_ids = {
        row[0]
        for row in conn.execute(
            "SELECT para_id FROM paragraphs_fts_porter WHERE paragraphs_fts_porter MATCH ?",
            (query,),
        ).fetchall()
    }
    return top, all_ids


def pg_matches(conn, query, limit, config):
    if config == "english":
        where = "search_vector @@ websearch_to_tsquery('english', %s)"
        rank = "ts_rank_cd(search_vector, websearch_to_tsquery('english', %s))"
        args = (query, query, limit)
    elif config == "simple":
        where = "to_tsvector('simple', text) @@ websearch_to_tsquery('simple', %s)"
        rank = "ts_rank_cd(to_tsvector('simple', text), websearch_to_tsquery('simple', %s))"
        args = (query, query, limit)
    else:
        raise ValueError(config)
    top = [
        row[0]
        for row in conn.execute(
            f"SELECT para_id FROM paragraphs WHERE {where} ORDER BY {rank} DESC LIMIT %s",
            args,
        ).fetchall()
    ]
    all_ids = {
        row[0]
        for row in conn.execute(
            f"SELECT para_id FROM paragraphs WHERE {where}",
            (query,),
        ).fetchall()
    }
    return top, all_ids


def metric(label, sqlite_top, sqlite_all, pg_top, pg_all, limit):
    s_top, p_top = set(sqlite_top), set(pg_top)
    common = len(s_top & p_top)
    union = len(s_top | p_top)
    match_union = len(sqlite_all | pg_all)
    match_common = len(sqlite_all & pg_all)
    return {
        "label": label,
        "sqlite_matches": len(sqlite_all),
        "postgres_matches": len(pg_all),
        "match_jaccard": round(match_common / match_union, 4) if match_union else 1.0,
        "top_common": common,
        "top_jaccard": round(common / union, 4) if union else 1.0,
        "sqlite_top_in_pg": len(s_top & pg_all),
        "postgres_top_in_sqlite": len(p_top & sqlite_all),
        "limit": limit,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fts-query", action="append", default=[])
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    source = assert_snapshot(args.source)
    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("psycopg is required", file=sys.stderr)
        return 2

    queries = args.fts_query or DEFAULT_QUERIES
    pg = psycopg.connect(dsn)
    rows = []
    try:
        with tempfile.TemporaryDirectory(prefix="scipal_fts_") as tmp:
            conn = sqlite3.connect(source)
            try:
                conn.execute(f"ATTACH DATABASE ? AS scratch", (str(Path(tmp) / "fts.db"),))
                # Build the porter table in the scratch database by copying
                # paragraphs; the source remains read-only.
                conn.execute(
                    "CREATE VIRTUAL TABLE scratch.paragraphs_fts_porter USING fts5("
                    "para_id UNINDEXED, paper_id UNINDEXED, text, tokenize='porter')"
                )
                conn.execute(
                    "INSERT INTO scratch.paragraphs_fts_porter (para_id, paper_id, text) "
                    "SELECT para_id, paper_id, text FROM main.paragraphs"
                )
                conn.commit()
                for query in queries:
                    unicode_top, unicode_all = sqlite_matches(conn, query, args.limit)
                    porter_top, porter_all = sqlite_porter_matches(conn, query, args.limit)
                    for config in ("english", "simple"):
                        pg_top, pg_all = pg_matches(pg, query, args.limit, config)
                        rows.append(
                            {
                                "query": query,
                                 "sqlite": "unicode61",
                                "postgres": config,
                                **metric(
                                    f"unicode61 vs {config}",
                                    unicode_top,
                                    unicode_all,
                                    pg_top,
                                    pg_all,
                                    args.limit,
                                ),
                            }
                        )
                        rows.append(
                            {
                                "query": query,
                                "sqlite": "porter",
                                "postgres": config,
                                **metric(
                                    f"porter vs {config}",
                                    porter_top,
                                    porter_all,
                                    pg_top,
                                    pg_all,
                                    args.limit,
                                ),
                            }
                        )
            finally:
                conn.close()
    finally:
        pg.close()

    report = {
        "source": str(source),
        "limit": args.limit,
        "queries": queries,
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
