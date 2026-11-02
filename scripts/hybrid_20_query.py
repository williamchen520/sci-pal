#!/usr/bin/env python3
"""20-query baseline for the existing HybridSearch (vector + FTS5 + RRF + rerank)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import _dedupe, load_cases, metrics, summarize  # noqa: E402
from services.search.rerank_client import RerankClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--rerank-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    from services.search.hybrid_search import HybridSearch

    cases = load_cases(ROOT / "eval" / "plugins" / "retriever_queries.json", args.per_source)
    search = HybridSearch()
    if not args.no_rerank and args.rerank_url:
        class ServiceReranker:
            def __init__(self, url):
                self.client = RerankClient(url)

            def rerank(self, query, results, top_k=5):
                if not results:
                    return []
                scores = self.client.score(
                    query,
                    [item.get("text", "")[:512] for item in results],
                    batch_size=8,
                    timeout=60,
                )
                for item, score in zip(results, scores):
                    item["rerank_score"] = score
                return sorted(results, key=lambda item: -item["rerank_score"])[:top_k]

        if not RerankClient(args.rerank_url).health():
            raise SystemExit(f"reranker service is not healthy: {args.rerank_url}")
        search._reranker = ServiceReranker(args.rerank_url)
    rows = []
    for case in cases:
        gold = set(case.get("gold_paper_ids") or [])
        if not gold:
            continue
        result = search.search(
            case["query"],
            top_k=args.top_k,
            rerank=not args.no_rerank,
        )
        ordered = _dedupe(item.get("paper_id") for item in result.get("results") or [])
        rows.append(
            {
                "case_id": case["case_id"],
                "source": case.get("source"),
                "query": case["query"],
                "system": "hybrid_rerank" if not args.no_rerank else "hybrid",
                "gold_count": len(gold),
                **metrics(ordered, gold),
            }
        )
        print(f"[{case['case_id']}] {rows[-1]}", file=sys.stderr, flush=True)

    report = {
        "cases": len(cases),
        "per_source": args.per_source,
        "top_k": args.top_k,
        "rerank": not args.no_rerank,
        "summary": [summarize(rows, "hybrid_rerank" if not args.no_rerank else "hybrid")],
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
