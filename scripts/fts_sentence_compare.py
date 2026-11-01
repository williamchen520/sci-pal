#!/usr/bin/env python3
"""20-query comparison: paragraph FTS vs v2 sentence-level FTS.

Metrics are paper-level: retrieve paragraphs/sentences, deduplicate to papers
in rank order, then score Recall@10, MRR, and nDCG@10 against gold paper IDs.
This is an evaluation only; it does not switch production search.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.fts_query_builder import _extract_keywords  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402

DEFAULT_CASES = ROOT / "eval" / "plugins" / "retriever_queries.json"
SOURCES = ("seed_100", "cross_topic", "claim_qualifiers", "paper_title")


def terms_for(query: str) -> list[str]:
    out = []
    for term in _extract_keywords(query):
        if term not in out:
            out.append(term)
    return out[:8]


def sqlite_paper_order(db: Path, terms: list[str], limit: int = 300) -> list[str]:
    if not terms:
        return []
    query = " OR ".join(f'"{term}"' for term in terms)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT paper_id FROM paragraphs_fts WHERE paragraphs_fts MATCH ? "
            "ORDER BY bm25(paragraphs_fts) LIMIT ?",
            (query, limit),
        ).fetchall()
    finally:
        conn.close()
    return _dedupe(paper_id for (paper_id,) in rows if paper_id)


def _dedupe(values) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def metrics(ranked: list[str], gold: set[str]) -> dict:
    top = ranked[:10]
    hit = set(top) & gold
    dcg = sum(1.0 / math.log2(i + 2) for i, pid in enumerate(top) if pid in gold)
    ideal_n = min(len(gold), 10)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
    mrr = 0.0
    for index, pid in enumerate(top, 1):
        if pid in gold:
            mrr = 1.0 / index
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
        selected.extend([c for c in cases if c.get("source") == source][:per_source])
    return selected[: per_source * len(SOURCES)]


def summarize(rows: list[dict], system: str) -> dict:
    subset = [row for row in rows if row["system"] == system]
    return {
        "system": system,
        "queries": len(subset),
        "recall@10": round(sum(r["recall@10"] for r in subset) / len(subset), 4) if subset else 0,
        "mrr": round(sum(r["mrr"] for r in subset) / len(subset), 4) if subset else 0,
        "ndcg@10": round(sum(r["ndcg@10"] for r in subset) / len(subset), 4) if subset else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")

    cases = load_cases(Path(args.cases), args.per_source)
    sentence_fts = SentenceFTS(args.pg_dsn)
    rows = []
    for case in cases:
        gold = set(case.get("gold_paper_ids") or [])
        terms = terms_for(case["query"])
        if not gold:
            continue
        paragraph_order = sqlite_paper_order(Path(args.sqlite_db), terms)
        sentence_hits = sentence_fts.search(case["query"], top_k=5000)
        sentence_order = _dedupe(hit.paper_id for hit in sentence_hits)
        for system, ranked in (
            ("paragraph_fts", paragraph_order),
            ("sentence_fts", sentence_order),
        ):
            rows.append(
                {
                    "case_id": case["case_id"],
                    "source": case.get("source"),
                    "query": case["query"],
                    "system": system,
                    "gold_count": len(gold),
                    **metrics(ranked, gold),
                }
            )

    report = {
        "cases": len(cases),
        "per_source": args.per_source,
        "refusal_accuracy": None,
        "note": "Retrieval-only comparison; refusal is not exercised in this run.",
        "summary": [
            summarize(rows, name) for name in ("paragraph_fts", "sentence_fts")
        ],
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
