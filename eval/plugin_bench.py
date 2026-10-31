#!/usr/bin/env python3
"""M0 plugin benchmark harness.

Usage:
    python eval/plugin_bench.py
    python eval/plugin_bench.py --plugins echo --dataset eval/plugins/demo_cases.json
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


def load_cases(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset must contain a non-empty 'cases' list")
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not isinstance(case.get("input"), dict):
            raise ValueError(f"case {index} must have an object 'input'")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugins", default="echo", help="comma-separated plugin ids")
    parser.add_argument("--dataset", default=str(ROOT / "eval" / "plugins" / "demo_cases.json"))
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "plugin_bench.jsonl"))
    parser.add_argument("--run-log", default=str(ROOT / "logs" / "plugin_runs.jsonl"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    cases = load_cases(dataset_path)
    ensure_benchmark_backend(papers=len(cases), concurrent=1)
    dataset_hash = "sha256:" + hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    plugin_ids = [item.strip() for item in args.plugins.split(",") if item.strip()]
    if not plugin_ids:
        raise ValueError("--plugins must not be empty")

    registry = PluginRegistry().load()
    runner = PluginRunner(registry, run_log=args.run_log)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    failures = 0
    for plugin_id in plugin_ids:
        for case in cases:
            try:
                run = runner.run(
                    plugin_id,
                    case["input"],
                    dataset_hash=dataset_hash,
                    seed=args.seed,
                )
                rows.append({"case_id": case.get("case_id"), "run": run.to_dict()})
            except Exception as exc:  # noqa: BLE001 - benchmark records failures
                failures += 1
                rows.append(
                    {
                        "case_id": case.get("case_id"),
                        "plugin_id": plugin_id,
                        "error": str(exc),
                    }
                )

    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    ok = len(rows) - failures
    summary = {
        "dataset": str(dataset_path),
        "dataset_hash": dataset_hash,
        "plugins": plugin_ids,
        "cases": len(cases),
        "runs": len(rows),
        "ok": ok,
        "failed": failures,
        "out": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
