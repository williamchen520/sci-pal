#!/usr/bin/env python3
"""Two-stage retrieval experiment: cheap GIN recall → cross-encoder rerank."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_rrf_compare import load_paragraph_texts, paragraph_candidates  # noqa: E402
from scripts.fts_sentence_compare import (  # noqa: E402
    _dedupe,
    load_cases,
    metrics,
    sqlite_paper_order,
    summarize,
    terms_for,
)
from services.search.rerank_client import RerankClient  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--recall", type=int, default=200)
    parser.add_argument("--terms", type=int, default=5)
    parser.add_argument("--ranker", default="rank", choices=("rank", "rank_cd"))
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if not RerankClient(args.url).health():
        raise SystemExit(f"reranker service is not healthy: {args.url}")

    cases = load_cases(ROOT / "eval" / "plugins" / "retriever_queries.json", args.per_source)
    sentence_fts = SentenceFTS(args.pg_dsn)
    rows = []
    failures = []
    for case in cases:
        gold = set(case.get("gold_paper_ids") or [])
        if not gold:
            continue
        paragraph_order = sqlite_paper_order(Path(args.sqlite_db), terms_for(case["query"]))
        hits = sentence_fts.search(case["query"], top_k=args.recall, term_limit=args.terms, ranker=args.ranker)
        candidates = paragraph_candidates(hits, args.recall)
        texts = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
        for candidate in candidates:
            candidate["text"] = (texts.get(candidate["para_id"]) or candidate["text"])[:512]
        try:
            scores = RerankClient(args.url).score(
                case["query"],
                [c["text"] for c in candidates],
                batch_size=8,
                timeout=60,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"case_id": case["case_id"], "error": str(exc)[:300]})
            continue
        for candidate, score in zip(candidates, scores):
            candidate["score"] = score
        reranked = sorted(candidates, key=lambda c: -c["score"])
        paper_order = _dedupe(c["paper_id"] for c in reranked)
        for system, ranked in (("paragraph_fts", paragraph_order), ("recall_rerank", paper_order)):
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
        "recall": args.recall,
        "ranker": args.ranker,
        "failures": failures,
        "summary": [summarize(rows, name) for name in ("paragraph_fts", "recall_rerank")],
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
