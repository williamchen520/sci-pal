#!/usr/bin/env python3
"""M2 retriever comparison harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.plugins import PluginRegistry, PluginRunner  # noqa: E402
from services.quality.benchmark_db import ensure_benchmark_backend  # noqa: E402

DEFAULT_PLUGINS = [
    "retriever-bm25",
    "retriever-dense",
    "retriever-hybrid",
    "retriever-hybrid-rerank",
]


def _dedupe_papers(candidates: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    ordered = []
    for item in candidates:
        paper_id = item.get("paper_id") or ""
        if paper_id and paper_id not in seen:
            seen.add(paper_id)
            ordered.append(paper_id)
    return ordered


def _score(candidates: List[Dict[str, Any]], gold: List[str], k: int = 10) -> Dict[str, float]:
    papers = _dedupe_papers(candidates)[:k]
    gold_set = set(gold)
    hits = [paper for paper in papers if paper in gold_set]
    recall = len(hits) / len(gold_set) if gold_set else 0.0
    mrr = 0.0
    for index, paper in enumerate(papers, start=1):
        if paper in gold_set:
            mrr = 1.0 / index
            break
    dcg = sum(1.0 / math.log2(index + 2) for index, paper in enumerate(papers) if paper in gold_set)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(gold_set), k)))
    ndcg = dcg / ideal if ideal else 0.0
    return {"recall@10": recall, "mrr": mrr, "ndcg@10": ndcg}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugins", default=",".join(DEFAULT_PLUGINS))
    parser.add_argument("--dataset", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "retriever_bench.jsonl"))
    parser.add_argument("--run-log", default=str(ROOT / "logs" / "plugin_runs.jsonl"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    plugin_ids = [item.strip() for item in args.plugins.split(",") if item.strip()]
    dataset_path = Path(args.dataset)
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))["cases"]
    ensure_benchmark_backend(papers=len(cases), concurrent=1)
    dataset_hash = "sha256:" + hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    registry = PluginRegistry().load()
    runner = PluginRunner(registry, run_log=args.run_log)

    rows: List[Dict[str, Any]] = []
    failures = 0
    for plugin_id in plugin_ids:
        for case in cases:
            try:
                run = runner.run(
                    plugin_id,
                    {
                        "query": case["query"],
                        "corpus": case["corpus"],
                        "top_k": args.top_k,
                    },
                    dataset_hash=dataset_hash,
                    seed=args.seed,
                )
                candidates = (run.output or {}).get("candidates") or []
                metrics = _score(candidates, case.get("gold_paper_ids") or [], args.top_k)
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "plugin_id": plugin_id,
                        "gold_paper_ids": case.get("gold_paper_ids") or [],
                        "candidates": [
                            {"paper_id": item.get("paper_id"), "node_id": item.get("node_id")}
                            for item in candidates
                        ],
                        "latency_ms": run.latency_ms,
                        **metrics,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                failures += 1
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "plugin_id": plugin_id,
                        "error": str(exc),
                    }
                )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    summary: Dict[str, Any] = {
        "dataset": str(dataset_path),
        "dataset_hash": dataset_hash,
        "plugins": plugin_ids,
        "cases": len(cases),
        "rows": len(rows),
        "failed": failures,
        "out": str(out_path),
        "per_plugin": {},
    }
    for plugin_id in plugin_ids:
        plugin_rows = [
            row for row in rows if row.get("plugin_id") == plugin_id and "recall@10" in row
        ]
        summary["per_plugin"][plugin_id] = {
            "scored": len(plugin_rows),
            "recall@10": round(
                sum(row["recall@10"] for row in plugin_rows) / len(plugin_rows), 4
            )
            if plugin_rows
            else 0.0,
            "mrr": round(sum(row["mrr"] for row in plugin_rows) / len(plugin_rows), 4)
            if plugin_rows
            else 0.0,
            "ndcg@10": round(
                sum(row["ndcg@10"] for row in plugin_rows) / len(plugin_rows), 4
            )
            if plugin_rows
            else 0.0,
            "avg_latency_ms": round(
                sum(row["latency_ms"] for row in plugin_rows) / len(plugin_rows), 1
            )
            if plugin_rows
            else 0.0,
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
