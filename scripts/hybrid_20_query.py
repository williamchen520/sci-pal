#!/usr/bin/env python3
"""20-query baseline for the existing HybridSearch (vector + FTS5 + RRF + rerank)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
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
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
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
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    rows = []
    for case in cases:
        gold = set(case.get("gold_paper_ids") or [])
        if not gold:
            continue
        gold_sentences = set(case.get("gold_sentence_ids") or [])
        gold_para = None
        if gold_sentences:
            marks = ",".join("?" * len(gold_sentences))
            row = db.execute(
                f"SELECT para_id FROM sentences WHERE sentence_id IN ({marks}) LIMIT 1",
                list(gold_sentences),
            ).fetchone()
            gold_para = row[0] if row else None
        started = time.perf_counter()
        result = search.search(
            case["query"],
            top_k=args.top_k,
            rerank=not args.no_rerank,
        )
        latency = time.perf_counter() - started
        hits = result.get("results") or []
        ordered = _dedupe(item.get("paper_id") for item in hits)
        rows.append(
            {
                "case_id": case["case_id"],
                "source": case.get("source"),
                "query": case["query"],
                "system": "hybrid_rerank" if not args.no_rerank else "hybrid",
                "gold_count": len(gold),
                "gold_paper_rank": next(
                    (i + 1 for i, paper in enumerate(ordered) if paper in gold), None
                ),
                "gold_sentence_rank": next(
                    (i + 1 for i, hit in enumerate(hits) if hit.get("para_id") == gold_para),
                    None,
                ) if gold_para else None,
                "latency_s": round(latency, 4),
                **metrics(ordered, gold),
            }
        )
        print(f"[{case['case_id']}] {rows[-1]}", file=sys.stderr, flush=True)

    db.close()
    system = "hybrid_rerank" if not args.no_rerank else "hybrid"
    summary = summarize(rows, system)
    latencies = sorted(row["latency_s"] for row in rows)
    def percentile(values, pct):
        if not values:
            return None
        index = min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1))))
        return values[index]
    summary["gold_sentence_top10"] = sum(
        1 for row in rows if row.get("gold_sentence_rank") and row["gold_sentence_rank"] <= 10
    )
    summary["latency_mean_s"] = round(sum(latencies) / len(latencies), 4) if latencies else None
    summary["latency_p50_s"] = percentile(latencies, 50)
    summary["latency_p95_s"] = percentile(latencies, 95)
    report = {
        "cases": len(cases),
        "per_source": args.per_source,
        "top_k": args.top_k,
        "rerank": not args.no_rerank,
        "summary": [summary],
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
