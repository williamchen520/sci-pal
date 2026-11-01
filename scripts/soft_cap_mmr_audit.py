#!/usr/bin/env python3
"""Offline audit: raw top-k vs soft per-paper cap vs MMR selection."""

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

from scripts.fts_sentence_compare import _dedupe, load_cases, metrics, terms_for  # noqa: E402
from services.search.diversity import select_diverse, diversity_report  # noqa: E402


def _rows(conn, terms, limit):
    query = " OR ".join(f'"{term}"' for term in terms)
    rows = conn.execute(
        "SELECT rowid, * FROM paragraphs_fts WHERE paragraphs_fts MATCH ? "
        "ORDER BY bm25(paragraphs_fts) LIMIT ?",
        (query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _gold_para(conn, sentence_ids):
    if not sentence_ids:
        return None
    placeholders = ",".join("?" * len(sentence_ids))
    row = conn.execute(
        f"SELECT para_id FROM sentences WHERE sentence_id IN ({placeholders}) LIMIT 1",
        list(sentence_ids),
    ).fetchone()
    return row[0] if row else None


def _evaluate(rows, gold_papers, gold_para):
    papers = _dedupe(row.get("paper_id") for row in rows)
    gold_para_rank = next(
        (i + 1 for i, row in enumerate(rows) if row.get("para_id") == gold_para),
        None,
    )
    return {
        "papers": papers,
        "gold_paper_rank": next((i + 1 for i, p in enumerate(papers) if p in gold_papers), None),
        "gold_sentence_rank": gold_para_rank if gold_para else None,
        "unique_papers": len(papers),
        "max_hits": max(Counter(row.get("paper_id") for row in rows).values()) if rows else 0,
        **metrics(papers, gold_papers),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--cases", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--depth", type=int, default=300)
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "soft_cap_mmr_audit.json"))
    args = parser.parse_args()

    cases = load_cases(Path(args.cases), 5)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows_out = []
    try:
        for case in cases:
            gold_papers = set(case.get("gold_paper_ids") or [])
            gold_para = _gold_para(conn, set(case.get("gold_sentence_ids") or []))
            terms = terms_for(case["query"])
            candidates = _rows(conn, terms, args.depth)
            variants = {
                "raw": candidates[:10],
                "cap2": select_diverse(candidates, top_k=10, max_per_paper=2, lambda_=1.0),
                "cap3": select_diverse(candidates, top_k=10, max_per_paper=3, lambda_=1.0),
                "mmr_cap3": select_diverse(candidates, top_k=10, max_per_paper=3, lambda_=0.75),
            }
            row = {"case_id": case["case_id"], "source": case.get("source")}
            for name, selected in variants.items():
                row[name] = _evaluate(selected, gold_papers, gold_para)
                row[name]["diversity"] = diversity_report(selected)
            rows_out.append(row)
    finally:
        conn.close()

    summary = {}
    for name in ("raw", "cap2", "cap3", "mmr_cap3"):
        summary[name] = {
            "recall@10": round(sum(r[name]["recall@10"] for r in rows_out) / len(rows_out), 4),
            "mrr": round(sum(r[name]["mrr"] for r in rows_out) / len(rows_out), 4),
            "ndcg@10": round(sum(r[name]["ndcg@10"] for r in rows_out) / len(rows_out), 4),
            "gold_sentence_top10": sum(
                1 for r in rows_out if r[name]["gold_sentence_rank"] and r[name]["gold_sentence_rank"] <= 10
            ),
            "mean_unique_papers@10": round(
                sum(r[name]["diversity"]["distinct_papers"] for r in rows_out) / len(rows_out), 3
            ),
            "mean_max_hits": round(
                sum(r[name]["diversity"]["max_hits_per_paper"] for r in rows_out) / len(rows_out), 3
            ),
        }
    report = {"summary": summary, "rows": rows_out}
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
