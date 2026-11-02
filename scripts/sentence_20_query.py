#!/usr/bin/env python3
"""20-query sentence-level evaluation: paragraph FTS vs sentence FTS.

Reports paper-level ranking, gold sentence rank, and latency. Read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import _dedupe, load_cases, metrics  # noqa: E402
from services.search.fts_query_builder import _extract_keywords  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def _gold_para(db: sqlite3.Connection, sentence_ids: set[str]) -> str | None:
    if not sentence_ids:
        return None
    marks = ",".join("?" * len(sentence_ids))
    row = db.execute(
        f"SELECT para_id FROM sentences WHERE sentence_id IN ({marks}) LIMIT 1",
        list(sentence_ids),
    ).fetchone()
    return row[0] if row else None


def _paragraph_hits(db: sqlite3.Connection, query: str, limit: int = 300) -> list[dict]:
    terms = _extract_keywords(query)
    if not terms:
        return []
    match = " OR ".join(f'"{term}"' for term in terms)
    rows = db.execute(
        "SELECT para_id, paper_id, text FROM paragraphs_fts "
        "WHERE paragraphs_fts MATCH ? ORDER BY bm25(paragraphs_fts) LIMIT ?",
        (match, limit),
    ).fetchall()
    return [{"para_id": r[0], "paper_id": r[1], "text": r[2]} for r in rows]


def _rank(values: list[str | None], target: str | None) -> int | None:
    if not target:
        return None
    for index, value in enumerate(values, 1):
        if value == target:
            return index
    return None


def _percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=100)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")

    cases = load_cases(ROOT / "eval" / "plugins" / "retriever_queries.json", args.per_source)
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    sentence_fts = SentenceFTS(args.pg_dsn)
    import psycopg
    rows = []
    try:
        for case in cases:
            gold_papers = set(case.get("gold_paper_ids") or [])
            gold_sentences = set(case.get("gold_sentence_ids") or [])
            gold_para = _gold_para(db, gold_sentences)
            pg_gold_sentences = set()
            if gold_sentences:
                marks = ",".join("?" * len(gold_sentences))
                for pid, text in db.execute(
                    f"SELECT paper_id, text FROM sentences WHERE sentence_id IN ({marks})",
                    list(gold_sentences),
                ):
                    with psycopg.connect(args.pg_dsn) as pg:
                        found = pg.execute(
                            "SELECT sentence_id FROM sentences WHERE paper_id=%s AND text=%s LIMIT 1",
                            (pid, text),
                        ).fetchone()
                    if found:
                        pg_gold_sentences.add(found[0])
            if not gold_papers:
                continue
            started = time.perf_counter()
            para_hits = _paragraph_hits(db, case["query"])
            para_latency = time.perf_counter() - started
            started = time.perf_counter()
            sent_hits = sentence_fts.search(case["query"], top_k=args.top_k)
            sent_latency = time.perf_counter() - started

            para_papers = _dedupe(hit["paper_id"] for hit in para_hits)
            sent_papers = _dedupe(hit.paper_id for hit in sent_hits)
            for system, paper_order, sentence_order, latency in (
                ("paragraph_fts", para_papers, [hit["para_id"] for hit in para_hits], para_latency),
                ("sentence_fts", sent_papers, [hit.sentence_id for hit in sent_hits], sent_latency),
            ):
                row = {
                    "case_id": case["case_id"],
                    "source": case.get("source"),
                    "system": system,
                    "gold_count": len(gold_papers),
                    "gold_sentence_rank": _rank(
                        sentence_order, next(iter(pg_gold_sentences), None)
                    ) if system == "sentence_fts" else None,
                    "gold_para_rank": _rank(
                        sentence_order if system == "paragraph_fts" else [hit.para_id for hit in sent_hits],
                        gold_para,
                    ),
                    "latency_s": round(latency, 4),
                    **metrics(paper_order, gold_papers),
                }
                rows.append(row)
            print(f"[{case['case_id']}] done", file=sys.stderr, flush=True)
    finally:
        db.close()

    summary = []
    for system in ("paragraph_fts", "sentence_fts"):
        subset = [row for row in rows if row["system"] == system]
        latencies = [row["latency_s"] for row in subset]
        summary.append(
            {
                "system": system,
                "queries": len(subset),
                "recall@10": round(sum(r["recall@10"] for r in subset) / len(subset), 4),
                "mrr": round(sum(r["mrr"] for r in subset) / len(subset), 4),
                "ndcg@10": round(sum(r["ndcg@10"] for r in subset) / len(subset), 4),
                "gold_sentence_top10": sum(
                    1 for row in subset if row["gold_sentence_rank"] and row["gold_sentence_rank"] <= 10
                ),
                "gold_para_top10": sum(
                    1 for row in subset if row["gold_para_rank"] and row["gold_para_rank"] <= 10
                ),
                "latency_mean_s": round(sum(latencies) / len(latencies), 4) if latencies else None,
                "latency_p50_s": _percentile(latencies, 50),
                "latency_p95_s": _percentile(latencies, 95),
            }
        )
    report = {"summary": summary, "rows": rows}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
