#!/usr/bin/env python3
"""20-query FTS comparison: SQLite unicode61 / SQLite porter / PostgreSQL english.

Uses gold paper ids from eval/plugins/retriever_queries.json and reports paper-level
Recall@10, MRR, nDCG@10. This is a benchmark, not a production switch.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.fts_query_builder import _extract_keywords  # noqa: E402

DEFAULT_CASES = ROOT / "eval" / "plugins" / "retriever_queries.json"
SOURCES = ("seed_100", "cross_topic", "claim_qualifiers", "paper_title")


def terms_for(query: str) -> list[str]:
    terms = []
    for term in _extract_keywords(query):
        if term not in terms:
            terms.append(term)
    return terms[:8]


def sqlite_papers(db: Path, fts_table: str, terms: list[str], limit: int) -> list[str]:
    if not terms:
        return []
    query = " OR ".join(f'"{term}"' for term in terms)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            f"SELECT paper_id FROM {fts_table} WHERE {fts_table} MATCH ? "
            f"ORDER BY bm25({fts_table}) LIMIT ?",
            (query, limit),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for (paper_id,) in rows:
        if paper_id and paper_id not in out:
            out.append(paper_id)
    return out[:10]


def pg_papers(conn, terms: list[str], config: str, limit: int) -> list[str]:
    if not terms:
        return []
    query = " | ".join(terms)
    if config == "english":
        sql = (
            "SELECT paper_id FROM paragraphs "
            "WHERE search_vector @@ to_tsquery('english', %s) "
            "ORDER BY ts_rank_cd(search_vector, to_tsquery('english', %s)) DESC "
            "LIMIT %s"
        )
    else:
        sql = (
            "SELECT paper_id FROM paragraphs "
            "WHERE to_tsvector('simple', text) @@ to_tsquery('simple', %s) "
            "ORDER BY ts_rank_cd(to_tsvector('simple', text), to_tsquery('simple', %s)) DESC "
            "LIMIT %s"
        )
    rows = conn.execute(sql, (query, query, limit)).fetchall()
    out = []
    for (paper_id,) in rows:
        if paper_id and paper_id not in out:
            out.append(paper_id)
    return out[:10]


def metrics(ranked: list[str], gold: set[str]) -> dict:
    top = ranked[:10]
    hit = set(top) & gold
    dcg = sum(1.0 / math.log2(i + 2) for i, p in enumerate(top) if p in gold)
    ideal_n = min(len(gold), 10)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
    mrr = 0.0
    for i, p in enumerate(top):
        if p in gold:
            mrr = 1.0 / (i + 1)
            break
    return {
        "recall@10": len(hit) / len(gold) if gold else 0.0,
        "mrr": mrr,
        "ndcg@10": dcg / idcg if idcg else 0.0,
    }


def load_cases(path: Path, per_source: int) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    selected = []
    for source in SOURCES:
        picked = [c for c in cases if c.get("source") == source][:per_source]
        selected.extend(picked)
    return selected[: per_source * len(SOURCES)]


def summarize(rows: list[dict], system: str) -> dict:
    subset = [row for row in rows if row["system"] == system]
    return {
        "system": system,
        "queries": len(subset),
        "recall@10": sum(r["recall@10"] for r in subset) / len(subset) if subset else 0,
        "mrr": sum(r["mrr"] for r in subset) / len(subset) if subset else 0,
        "ndcg@10": sum(r["ndcg@10"] for r in subset) / len(subset) if subset else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unicode-source", required=True)
    parser.add_argument("--porter-source", required=True)
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("psycopg is required", file=sys.stderr)
        return 2

    cases = load_cases(Path(args.cases), args.per_source)
    pg = psycopg.connect(dsn)
    rows = []
    try:
        for case in cases:
            terms = terms_for(case["query"])
            gold = set(case.get("gold_paper_ids") or [])
            if not gold:
                continue
            systems = {
                "sqlite_unicode": sqlite_papers(
                    Path(args.unicode_source), "paragraphs_fts", terms, 300
                ),
                "sqlite_porter": sqlite_papers(
                    Path(args.porter_source), "paragraphs_fts", terms, 300
                ),
                "pg_english": pg_papers(pg, terms, "english", 300),
            }
            for system, ranked in systems.items():
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "source": case["source"],
                        "query": case["query"],
                        "terms": terms,
                        "system": system,
                        "gold_count": len(gold),
                        **metrics(ranked, gold),
                    }
                )
    finally:
        pg.close()

    report = {
        "cases": len(cases),
        "per_source": args.per_source,
        "rows": rows,
        "summary": [
            summarize(rows, name)
            for name in ("sqlite_unicode", "sqlite_porter", "pg_english")
        ],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
