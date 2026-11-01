#!/usr/bin/env python3
"""Paper-level RRF experiment:
paragraph FTS + sentence FTS -> paragraph -> cross-encoder -> RRF over paper ranks.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

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
from services.search.rerank_worker import RerankWorker  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402




def paragraph_candidates(hits, max_paragraphs):
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


def load_paragraph_texts(dsn, para_ids):
    if not para_ids:
        return {}
    import psycopg

    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT para_id, text FROM paragraphs WHERE para_id = ANY(%s)",
            (para_ids,),
        ).fetchall()
    return {row[0]: row[1] for row in rows}

def rrf(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, paper_id in enumerate(_dedupe(ranked), 1):
            scores[paper_id] = scores.get(paper_id, 0.0) + 1.0 / (k + rank)
    return [paper_id for paper_id, _ in sorted(scores.items(), key=lambda x: -x[1])]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--cases", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--candidate-counts", default="20,50")
    parser.add_argument("--out", default="")
    parser.add_argument("--rerank-timeout", type=float, default=15.0)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--max-failures", type=int, default=20)
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")

    counts = [int(x) for x in args.candidate_counts.split(",") if x.strip()]
    reranker = RerankWorker(timeout=args.startup_timeout)
    sentence_fts = SentenceFTS(args.pg_dsn)
    cases = load_cases(Path(args.cases), args.per_source)
    rows = []
    failures = []

    stopped_early = False
    for case in cases:
        if stopped_early:
            break
        gold = set(case.get("gold_paper_ids") or [])
        terms = terms_for(case["query"])
        if not gold:
            continue
        paragraph_order = sqlite_paper_order(Path(args.sqlite_db), terms)
        hits = sentence_fts.search(case["query"], top_k=1000)
        rows.append(
            {
                "case_id": case["case_id"],
                "source": case.get("source"),
                "system": "paragraph_fts",
                "candidates": None,
                "gold_count": len(gold),
                **metrics(paragraph_order, gold),
            }
        )
        for count in counts:
            candidates = paragraph_candidates(hits, count)
            texts = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
            for candidate in candidates:
                candidate["text"] = (texts.get(candidate["para_id"]) or candidate["text"])[:512]
            try:
                scores = reranker.score(
                    case["query"],
                    [candidate["text"] for candidate in candidates],
                    batch_size=8,
                    timeout=args.rerank_timeout,
                )
            except (TimeoutError, RuntimeError) as exc:
                failures.append(
                    {
                        "case_id": case["case_id"],
                        "candidates": count,
                        "error": str(exc)[:300],
                    }
                )
                if len(failures) >= args.max_failures:
                    stopped_early = True
                    break
                continue
            for candidate, score in zip(candidates, scores):
                candidate["rerank_score"] = score
            reranked = sorted(candidates, key=lambda item: -item["rerank_score"])
            sentence_order = _dedupe(item["paper_id"] for item in reranked)
            fused_order = rrf([paragraph_order, sentence_order])
            for system, ranked in (
                (f"multistage_{count}", sentence_order),
                (f"rrf_{count}", fused_order),
            ):
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "source": case.get("source"),
                        "system": system,
                        "candidates": count,
                        "gold_count": len(gold),
                        **metrics(ranked, gold),
                    }
                )

    names = ["paragraph_fts"]
    for count in counts:
        names.extend([f"multistage_{count}", f"rrf_{count}"])
    reranker.close()
    report = {
        "cases": len(cases),
        "candidate_counts": counts,
        "failures": failures,
        "failure_count": len(failures),
        "partial": bool(failures) or stopped_early,
        "summary": [summarize(rows, name) for name in names],
        "rows": rows,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
