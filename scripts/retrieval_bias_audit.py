#!/usr/bin/env python3
"""Bias audit: paper-level recall can hide per-document duplication and sentence misses."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import _dedupe, load_cases, metrics, summarize, terms_for  # noqa: E402
from services.search.dedup import suppress_near_duplicates  # noqa: E402


def _fts_rows(conn, table: str, terms: list[str], limit: int) -> list[dict]:
    if not terms:
        return []
    query = " OR ".join(f'"{term}"' for term in terms)
    rows = conn.execute(
        f"SELECT rowid, * FROM {table} WHERE {table} MATCH ? "
        f"ORDER BY bm25({table}) LIMIT ?",
        (query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _order(rows: list[dict]) -> tuple[list[str], Counter]:
    papers = []
    counts = Counter()
    for row in rows:
        paper = row.get("paper_id")
        if not paper:
            continue
        counts[paper] += 1
        if paper not in papers:
            papers.append(paper)
    return papers, counts


def _metrics_for(ranked: list[str], gold: set[str]) -> dict:
    return metrics(ranked, gold)


def _cap_rows(rows, *, top_n=10, max_per_paper=2):
    counts = Counter()
    selected = []
    for row in rows:
        paper = row.get("paper_id")
        if not paper:
            continue
        if counts[paper] >= max_per_paper:
            continue
        counts[paper] += 1
        selected.append(row)
        if len(selected) >= top_n:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--cases", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--depth", type=int, default=1000)
    parser.add_argument("--near-dup-threshold", type=float, default=0.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    cases = load_cases(Path(args.cases), args.per_source)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = []
    try:
        for case in cases:
            gold_papers = set(case.get("gold_paper_ids") or [])
            gold_sentences = set(case.get("gold_sentence_ids") or [])
            terms = terms_for(case["query"])
            para_rows = _fts_rows(conn, "paragraphs_fts", terms, args.depth)
            sent_rows = _fts_rows(conn, "sentences_fts", terms, args.depth)
            para_papers, para_counts = _order(para_rows)
            sent_papers, sent_counts = _order(sent_rows)
            gold_paper_rank = next(
                (i + 1 for i, pid in enumerate(para_papers) if pid in gold_papers), None
            )
            gold_sent_rank = None
            if gold_sentences:
                for i, row in enumerate(sent_rows):
                    if row.get("sentence_id") in gold_sentences:
                        gold_sent_rank = i + 1
                        break
            top10_rows = para_rows[:10]
            top10 = _dedupe(row.get("paper_id") for row in top10_rows)
            top10_unique = len(set(top10))
            top10_counts = Counter(row.get("paper_id") for row in top10_rows if row.get("paper_id"))
            near_rows = []
            if args.near_dup_threshold > 0:
                near_input = []
                for row in para_rows:
                    item = dict(row)
                    item["score"] = -float(item.get("score") or 0)
                    near_input.append(item)
                near_rows = suppress_near_duplicates(
                    near_input,
                    threshold=args.near_dup_threshold,
                    text_key="text",
                    paper_key="paper_id",
                    id_keys=("para_id",),
                    score_key="score",
                )
            near_papers, near_counts = _order(near_rows)
            near_top10 = _dedupe(row.get("paper_id") for row in near_rows[:10])
            near_gold_paper_rank = next(
                (i + 1 for i, pid in enumerate(near_papers) if pid in gold_papers), None
            )
            gold_para = None
            if gold_sentences:
                ids = list(gold_sentences)
                placeholders = ",".join("?" * len(ids))
                row = conn.execute(
                    f"SELECT para_id FROM sentences WHERE sentence_id IN ({placeholders}) LIMIT 1",
                    ids,
                ).fetchone()
                gold_para = row[0] if row else None
            near_gold_sent_rank = next(
                (i + 1 for i, row in enumerate(near_rows) if row.get("para_id") == gold_para),
                None,
            ) if gold_para else None
            cap_rows = _cap_rows(para_rows, top_n=10, max_per_paper=2)
            cap_papers = _dedupe(row.get("paper_id") for row in cap_rows)
            cap_gold_paper_rank = next(
                (i + 1 for i, pid in enumerate(cap_papers) if pid in gold_papers), None
            )
            cap_gold_sent_rank = next(
                (i + 1 for i, row in enumerate(cap_rows) if row.get("para_id") == gold_para),
                None,
            )
            rows.append(
                {
                    "case_id": case["case_id"],
                    "source": case.get("source"),
                    "gold_papers": len(gold_papers),
                    "gold_sentences": len(gold_sentences),
                    "paragraph_candidates": len(para_rows),
                    "unique_papers": len(para_counts),
                    "unique_papers@10": top10_unique,
                    "max_hits_per_paper": max(para_counts.values()) if para_counts else 0,
                    "max_hits_per_paper@10": max(top10_counts.values()) if top10_counts else 0,
                    "top10_paper_ids": top10,
                    "gold_paper_rank": gold_paper_rank,
                    "cap2_unique_papers@10": len(set(cap_papers)),
                    "cap2_gold_paper_rank": cap_gold_paper_rank,
                    "cap2_gold_sentence_rank": cap_gold_sent_rank,
                    "cap2_recall@10": _metrics_for(cap_papers, gold_papers)["recall@10"],
                    "cap2_mrr": _metrics_for(cap_papers, gold_papers)["mrr"],
                    "cap2_ndcg@10": _metrics_for(cap_papers, gold_papers)["ndcg@10"],
                    "near_unique_papers": len(near_counts),
                    "near_unique_papers@10": len(set(near_top10)),
                    "near_max_hits_per_paper": max(near_counts.values()) if near_counts else 0,
                    "near_gold_paper_rank": near_gold_paper_rank,
                    "near_gold_sentence_rank": near_gold_sent_rank,
                    "near_recall@10": _metrics_for(near_papers, gold_papers)["recall@10"],
                    "near_mrr": _metrics_for(near_papers, gold_papers)["mrr"],
                    "near_ndcg@10": _metrics_for(near_papers, gold_papers)["ndcg@10"],
                    "sentence_candidates": len(sent_rows),
                    "sentence_unique_papers": len(sent_counts),
                    "gold_sentence_rank": gold_sent_rank,
                    **_metrics_for(para_papers, gold_papers),
                }
            )
    finally:
        conn.close()

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
        "cap2_mean_unique_papers@10": round(
            sum(r["cap2_unique_papers@10"] for r in rows) / len(rows), 3
        ) if rows else 0,
        "cap2_gold_paper_top10": sum(
            1 for r in rows if r["cap2_gold_paper_rank"] and r["cap2_gold_paper_rank"] <= 10
        ),
        "cap2_gold_sentence_top10": sum(
            1 for r in rows if r["cap2_gold_sentence_rank"] and r["cap2_gold_sentence_rank"] <= 10
        ),
        "near_dup_threshold": args.near_dup_threshold,
        "near_mean_unique_papers@10": round(
            sum(r["near_unique_papers@10"] for r in rows) / len(rows), 3
        ) if rows and args.near_dup_threshold > 0 else None,
        "near_gold_paper_top10": sum(
            1 for r in rows if r["near_gold_paper_rank"] and r["near_gold_paper_rank"] <= 10
        ) if args.near_dup_threshold > 0 else None,
        "near_gold_sentence_top10": sum(
            1 for r in rows if r["near_gold_sentence_rank"] and r["near_gold_sentence_rank"] <= 10
        ) if args.near_dup_threshold > 0 else None,
        "near_paper_metrics": {
            "queries": len(rows),
            "recall@10": round(sum(r["near_recall@10"] for r in rows) / len(rows), 4) if rows and args.near_dup_threshold > 0 else None,
            "mrr": round(sum(r["near_mrr"] for r in rows) / len(rows), 4) if rows and args.near_dup_threshold > 0 else None,
            "ndcg@10": round(sum(r["near_ndcg@10"] for r in rows) / len(rows), 4) if rows and args.near_dup_threshold > 0 else None,
        },
        "cap2_paper_metrics": {
            "queries": len(rows),
            "recall@10": round(sum(r["cap2_recall@10"] for r in rows) / len(rows), 4) if rows else 0,
            "mrr": round(sum(r["cap2_mrr"] for r in rows) / len(rows), 4) if rows else 0,
            "ndcg@10": round(sum(r["cap2_ndcg@10"] for r in rows) / len(rows), 4) if rows else 0,
        },
        "paper_metrics": summarize(
            [{"system": "paper_fts", **row} for row in rows], "paper_fts"
        ),
    }
    report = {"summary": summary, "rows": rows}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
