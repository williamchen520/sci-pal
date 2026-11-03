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


def _load_cases(path: Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases") or payload


def _case_id(case: dict) -> str:
    return case.get("case_id") or case.get("id") or ""


def _query(case: dict) -> str:
    return case.get("query") or case.get("question") or ""


def _gold_para(case: dict) -> str:
    for sentence_id in case.get("gold_sentence_ids") or case.get("evidence") or []:
        if "_sent_" in sentence_id:
            return sentence_id.rsplit("_sent_", 1)[0]
    return ""


def _rrf(pg_ids: list[str], reranked_ids: list[str], *, k: int = 60, top_k: int = 10) -> list[str]:
    scores: dict[str, float] = {}
    for rank, pid in enumerate(pg_ids, 1):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    for rank, pid in enumerate(reranked_ids, 1):
        scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
    return [pid for pid, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]]


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
    parser.add_argument("--no-fusion", action="store_true")
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--out", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-rerank.json"))
    parser.add_argument("--out-md", default=str(ROOT / "docs" / "PostgreSQL迁移-FTS-rerank.md"))
    args = parser.parse_args()
    if not args.pg_dsn:
        print("--pg-dsn is required", file=sys.stderr)
        return 2

    cases = _load_cases(Path(args.queries))
    cases = cases[: args.limit]
    reranker = None if args.no_rerank else Reranker()
    rows = []
    pg_fts = PGParagraphFTS(args.pg_dsn, ranker="rank")
    try:
        for case in cases:
            query = _query(case)
            gold = _gold_para(case)
            sqlite_ids = _sqlite_ids(args.db, "paragraphs_fts", "para_id", query, args.top_k)
            started = time.perf_counter()
            candidates = pg_fts.search(query, top_k=args.candidates, term_limit=4)
            pg_seconds = time.perf_counter() - started
            pg_ids = [hit.para_id for hit in candidates][: args.top_k]
            reranked_ids = []
            reranked_all = []
            rerank_seconds = 0.0
            if reranker is not None:
                started = time.perf_counter()
                reranked = reranker.rerank(
                    query,
                    [{"para_id": hit.para_id, "text": hit.text} for hit in candidates],
                    top_k=len(candidates),
                )
                rerank_seconds = time.perf_counter() - started
                reranked_all = [row["para_id"] for row in reranked]
                reranked_ids = reranked_all[: args.top_k]
            fused_ids = reranked_ids
            if reranked_all and not args.no_fusion:
                fused_ids = _rrf([h.para_id for h in candidates], reranked_all, k=args.rrf_k, top_k=args.top_k)
            rows.append(
                {
                    "case": _case_id(case),
                    "gold": gold,
                    "sqlite_top10": sqlite_ids,
                    "pg_top10": pg_ids,
                    "pg_rerank_top10": reranked_ids,
                    "sqlite_ndcg": _ndcg(sqlite_ids, gold),
                    "pg_ndcg": _ndcg(pg_ids, gold),
                    "pg_rerank_ndcg": _ndcg(reranked_ids, gold),
                    "fused_top10": fused_ids,
                    "fused_ndcg": _ndcg(fused_ids, gold),
                    "pg_seconds": round(pg_seconds, 3),
                    "rerank_seconds": round(rerank_seconds, 3),
                }
            )
            print(f"[{_case_id(case)}]", flush=True)
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
            for key in ("sqlite_ndcg", "pg_ndcg", "pg_rerank_ndcg", "fused_ndcg", "pg_seconds", "rerank_seconds")
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
        f"> PG+rerank+RRF nDCG: {report['avg']['fused_ndcg']:.3f}  ",
        f"> PG seconds: {report['avg']['pg_seconds']:.2f}  ",
        f"> rerank seconds: {report['avg']['rerank_seconds']:.2f}",
        "",
        "| case | sqlite nDCG | pg nDCG | pg+rerank nDCG | fused nDCG |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['sqlite_ndcg']:.3f} | {row['pg_ndcg']:.3f} | {row['pg_rerank_ndcg']:.3f} | {row['fused_ndcg']:.3f} |"
        )
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["avg"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
