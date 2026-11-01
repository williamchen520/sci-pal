#!/usr/bin/env python3
"""Bias audit for HybridSearch: paper-level vs sentence-level, and per-document duplication."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import _dedupe, load_cases, metrics  # noqa: E402


def sentence_para_map(conn, sentence_ids):
    ids = [sid for sid in sentence_ids if sid]
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT sentence_id, para_id FROM sentences WHERE sentence_id IN ({placeholders})",
        ids,
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from services.search.hybrid_search import HybridSearch

    cases = load_cases(ROOT / "eval" / "plugins" / "retriever_queries.json", args.per_source)
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'research.db'}?mode=ro", uri=True)
    search = HybridSearch()
    rows = []
    for case in cases:
        gold_papers = set(case.get("gold_paper_ids") or [])
        gold_sents = set(case.get("gold_sentence_ids") or [])
        sent_para = sentence_para_map(db, gold_sents)
        expected_paras = set(sent_para.values())
        result = search.search(
            case["query"], top_k=args.top_k, rerank=False, expand_queries=False
        )
        hits = result.get("results") or []
        papers = _dedupe(hit.get("paper_id") for hit in hits)
        counts = Counter(hit.get("paper_id") for hit in hits if hit.get("paper_id"))
        gold_paper_rank = next((i + 1 for i, p in enumerate(papers) if p in gold_papers), None)
        gold_sent_rank = None
        for i, hit in enumerate(hits):
            if hit.get("para_id") in expected_paras:
                gold_sent_rank = i + 1
                break
        rows.append(
            {
                "case_id": case["case_id"],
                "source": case.get("source"),
                "gold_papers": len(gold_papers),
                "gold_sentences": len(gold_sents),
                "returned_paragraphs": len(hits),
                "unique_papers": len(papers),
                "unique_papers@10": len(papers[:10]),
                "max_hits_per_paper": max(counts.values()) if counts else 0,
                "top10_paper_ids": papers[:10],
                "gold_paper_rank": gold_paper_rank,
                "gold_sentence_rank": gold_sent_rank,
                **metrics(papers, gold_papers),
            }
        )
        print(f"[{case['case_id']}] {rows[-1]}", file=sys.stderr, flush=True)

    db.close()
    summary = {
        "cases": len(rows),
        "gold_papers_total": sum(r["gold_papers"] for r in rows),
        "queries_with_multiple_gold_papers": sum(1 for r in rows if r["gold_papers"] > 1),
        "mean_unique_papers@10": round(
            sum(r["unique_papers@10"] for r in rows) / len(rows), 3
        )
        if rows
        else 0,
        "mean_max_hits_per_paper": round(
            sum(r["max_hits_per_paper"] for r in rows) / len(rows), 3
        )
        if rows
        else 0,
        "gold_paper_top10": sum(1 for r in rows if r["gold_paper_rank"] and r["gold_paper_rank"] <= 10),
        "gold_sentence_top10": sum(
            1 for r in rows if r["gold_sentence_rank"] and r["gold_sentence_rank"] <= 10
        ),
        "paper_metrics": {
            "queries": len(rows),
            "recall@10": round(sum(r["recall@10"] for r in rows) / len(rows), 4) if rows else 0,
            "mrr": round(sum(r["mrr"] for r in rows) / len(rows), 4) if rows else 0,
            "ndcg@10": round(sum(r["ndcg@10"] for r in rows) / len(rows), 4) if rows else 0,
        },
    }
    report = {"summary": summary, "rows": rows}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
