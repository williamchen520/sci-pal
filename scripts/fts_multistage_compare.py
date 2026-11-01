#!/usr/bin/env python3
"""Multi-stage retrieval experiment:
sentence FTS recall -> paragraph aggregation -> cross-encoder rerank -> paper ranking.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import (  # noqa: E402
    _dedupe,
    load_cases,
    metrics,
    sqlite_paper_order,
    summarize,
    terms_for,
)
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def paragraph_candidates(hits, max_paragraphs: int):
    best = {}
    for hit in hits:
        current = best.get(hit.para_id)
        if current is None or hit.rank > current["rank"]:
            best[hit.para_id] = {
                "para_id": hit.para_id,
                "paper_id": hit.paper_id,
                "text": hit.text,
                "rank": hit.rank,
            }
    return list(best.values())[:max_paragraphs]


def load_paragraph_texts(dsn: str, para_ids: list[str]) -> dict[str, str]:
    if not para_ids:
        return {}
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT para_id, text FROM paragraphs WHERE para_id = ANY(%s)",
            (para_ids,),
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--cases", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--max-paragraphs", type=int, default=80)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")

    from services.search.reranker import Reranker

    reranker = Reranker()
    cases = load_cases(Path(args.cases), args.per_source)
    sentence_fts = SentenceFTS(args.pg_dsn)
    rows = []

    for case in cases:
        gold = set(case.get("gold_paper_ids") or [])
        terms = terms_for(case["query"])
        if not gold:
            continue
        paragraph_order = sqlite_paper_order(Path(args.sqlite_db), terms)
        hits = sentence_fts.search(case["query"], top_k=5000)
        candidates = paragraph_candidates(hits, args.max_paragraphs)
        texts = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
        for candidate in candidates:
            candidate["text"] = (texts.get(candidate["para_id"]) or candidate["text"])[:1500]
        reranked = reranker.rerank(case["query"], candidates, top_k=len(candidates))
        multistage_order = _dedupe(item["paper_id"] for item in reranked)
        for system, ranked in (
            ("paragraph_fts", paragraph_order),
            ("sentence_multistage", multistage_order),
        ):
            rows.append(
                {
                    "case_id": case["case_id"],
                    "source": case.get("source"),
                    "system": system,
                    "gold_count": len(gold),
                    **metrics(ranked, gold),
                }
            )

    report = {
        "cases": len(cases),
        "candidate_paragraphs": args.max_paragraphs,
        "summary": [
            summarize(rows, name) for name in ("paragraph_fts", "sentence_multistage")
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
