#!/usr/bin/env python3
"""Shadow-ready PG FTS candidate recall + cross-encoder rerank evaluation."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fts_shadow_compare import _sqlite_ids  # noqa: E402
from services.db.pg_pool import close_pools  # noqa: E402
from services.search.pg_fts import PGParagraphFTS  # noqa: E402
from services.search.reranker import Reranker  # noqa: E402


def _gold_para(case: dict) -> str:
    for sentence_id in case.get("gold_sentence_ids") or []:
        if "_sent_" in sentence_id:
            return sentence_id.rsplit("_sent_", 1)[0]
    return ""


def _ndcg(ids: list[str], gold: str) -> float:
    if not gold or gold not in ids:
        return 0.0
    rank = ids.index(gold) + 1
    return 1.0 / math.log2(rank + 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--queries", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=50)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-rerank.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-rerank.md"))
    args = parser.parse_args()
    if not args.pg_dsn:
        print("--pg-dsn is required", file=sys.stderr)
        return 2

    cases = json.loads(Path(args.queries).read_text(encoding="utf-8")).get("cases") or []
    cases = cases[: args.limit]
    reranker = None if args.no_rerank else Reranker()
    rows = []
    pg_fts = PGParagraphFTS(args.pg_dsn, ranker="rank")
    try:
        for case in cases:
            query = case["query"]
            gold = _gold_para(case)
            sqlite_ids = _sqlite_ids(args.db, "paragraphs_fts", "para_id", query, args.top_k)
            started = time.perf_counter()
            candidates = pg_fts.search(query, top_k=args.candidates, term_limit=4)
            pg_seconds = time.perf_counter() - started
            pg_ids = [hit.para_id for hit in candidates][: args.top_k]
            reranked_ids = []
            rerank_seconds = 0.0
            if reranker is not None:
                started = time.perf_counter()
                reranked = reranker.rerank(
                    query,
                    [{"para_id": hit.para_id, "text": hit.text} for hit in candidates],
                    top_k=args.top_k,
                )
                rerank_seconds = time.perf_counter() - started
                reranked_ids = [row["para_id"] for row in reranked]
            rows.append(
                {
                    "case": case["case_id"],
                    "gold": gold,
                    "sqlite_top10": sqlite_ids,
                    "pg_top10": pg_ids,
                    "pg_rerank_top10": reranked_ids,
                    "sqlite_ndcg": _ndcg(sqlite_ids, gold),
                    "pg_ndcg": _ndcg(pg_ids, gold),
                    "pg_rerank_ndcg": _ndcg(reranked_ids, gold),
                    "pg_seconds": round(pg_seconds, 3),
                    "rerank_seconds": round(rerank_seconds, 3),
                }
            )
            print(f"[{case['case_id']}]", flush=True)
    finally:
        close_pools()

    def avg(key: str) -> float:
        return sum(row[key] for row in rows) / max(len(rows), 1)

    report = {
        "queries": len(rows),
        "top_k": args.top_k,
        "candidates": args.candidates,
        "avg": {
            key: avg(key)
            for key in ("sqlite_ndcg", "pg_ndcg", "pg_rerank_ndcg", "pg_seconds", "rerank_seconds")
        },
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# PG FTS + Rerank Shadow",
        "",
        f"> queries: {report['queries']}  ",
        f"> candidates: {args.candidates}  ",
        f"> SQLite nDCG: {report['avg']['sqlite_ndcg']:.3f}  ",
        f"> PG nDCG: {report['avg']['pg_ndcg']:.3f}  ",
        f"> PG+rerank nDCG: {report['avg']['pg_rerank_ndcg']:.3f}  ",
        f"> PG seconds: {report['avg']['pg_seconds']:.2f}  ",
        f"> rerank seconds: {report['avg']['rerank_seconds']:.2f}",
        "",
        "| case | sqlite nDCG | pg nDCG | pg+rerank nDCG |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['sqlite_ndcg']:.3f} | {row['pg_ndcg']:.3f} | {row['pg_rerank_ndcg']:.3f} |"
        )
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["avg"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
