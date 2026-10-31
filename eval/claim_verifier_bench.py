#!/usr/bin/env python3
"""M1 claim-verifier comparison harness.

Compares adapters on the 10-claim pilot. It never writes claim cards or evidence
tables; each call is a read-only plugin run recorded in JSONL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.plugins import PluginRegistry, PluginRunner  # noqa: E402
from services.quality.benchmark_db import ensure_benchmark_backend  # noqa: E402

DEFAULT_PLUGINS = ["claim-verifier-rule", "claim-verifier-underdetermines"]


def _accuracy(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [row for row in rows if row.get("gold_relation")]
    correct = sum(
        1
        for row in scored
        if row.get("relation") and row["relation"] == row["gold_relation"]
    )
    by_relation: Dict[str, Dict[str, int]] = {}
    for row in scored:
        bucket = by_relation.setdefault(row["gold_relation"], {"total": 0, "correct": 0})
        bucket["total"] += 1
        if row.get("relation") == row["gold_relation"]:
            bucket["correct"] += 1
    return {
        "scored": len(scored),
        "correct": correct,
        "accuracy": round(correct / len(scored), 4) if scored else 0.0,
        "by_gold_relation": by_relation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugins", default=",".join(DEFAULT_PLUGINS))
    parser.add_argument("--include-nli", action="store_true")
    parser.add_argument(
        "--dataset", default=str(ROOT / "eval" / "plugins" / "claims_pilot_cases.json")
    )
    parser.add_argument(
        "--out", default=str(ROOT / "eval" / "results" / "claim_verifier_bench.jsonl")
    )
    parser.add_argument("--run-log", default=str(ROOT / "logs" / "plugin_runs.jsonl"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    plugin_ids = [item.strip() for item in args.plugins.split(",") if item.strip()]
    if args.include_nli and "claim-verifier-nli" not in plugin_ids:
        plugin_ids.append("claim-verifier-nli")

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
            payload = {
                "claim": case["claim"],
                "evidence": [
                    {
                        "evidence_id": item["evidence_id"],
                        "paper_id": item.get("paper_id") or "",
                        "quote": item["quote"],
                    }
                    for item in case["evidence"]
                ],
            }
            try:
                run = runner.run(
                    plugin_id,
                    payload,
                    dataset_hash=dataset_hash,
                    seed=args.seed,
                )
                by_id = {
                    item["evidence_id"]: item
                    for item in (run.output or {}).get("verifications", [])
                }
                for item in case["evidence"]:
                    predicted = by_id.get(item["evidence_id"]) or {}
                    rows.append(
                        {
                            "case_id": case["case_id"],
                            "plugin_id": plugin_id,
                            "evidence_id": item["evidence_id"],
                            "gold_relation": item.get("gold_relation"),
                            "relation": predicted.get("relation"),
                            "confidence": predicted.get("confidence"),
                            "rationale": predicted.get("rationale"),
                            "latency_ms": run.latency_ms,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - benchmark records failures
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
        plugin_rows = [row for row in rows if row.get("plugin_id") == plugin_id]
        summary["per_plugin"][plugin_id] = _accuracy(plugin_rows)
    gold_counts: Dict[str, int] = {}
    for row in rows:
        gold = row.get("gold_relation")
        if gold:
            gold_counts[gold] = gold_counts.get(gold, 0) + 1
    if gold_counts:
        summary["majority_baseline"] = {
            "label": max(gold_counts, key=gold_counts.get),
            "accuracy": round(max(gold_counts.values()) / sum(gold_counts.values()), 4),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
