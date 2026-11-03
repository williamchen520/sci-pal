"""Compare evaluation results against a baseline (CI gate)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict


def compare(
    baseline: Dict,
    current: Dict,
    tolerance: float = 0.02,
    baseline_ids: list[str] | None = None,
    current_ids: list[str] | None = None,
) -> Dict:
    keys = [key for key in baseline if key.startswith(("recall@", "ndcg@")) or key == "mrr"]
    failures = []
    if baseline_ids is not None and current_ids is not None:
        base_set, cur_set = set(baseline_ids), set(current_ids)
        if base_set != cur_set:
            failures.append(
                {
                    "metric": "gold_id_set",
                    "baseline": sorted(base_set - cur_set)[:20],
                    "current": sorted(cur_set - base_set)[:20],
                }
            )
    for key in keys:
        base = float(baseline.get(key) or 0.0)
        cur = float(current.get(key) or 0.0)
        if cur < base - tolerance:
            failures.append({"metric": key, "baseline": base, "current": cur})
    return {"ok": not failures, "failures": failures}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()
    baseline_doc = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    current_doc = json.loads(Path(args.current).read_text(encoding="utf-8"))
    baseline = baseline_doc["summary"]
    current = current_doc["summary"]
    baseline_ids = [row["id"] for row in baseline_doc.get("rows") or []]
    current_ids = [row["id"] for row in current_doc.get("rows") or []]
    result = compare(baseline, current, args.tolerance, baseline_ids or None, current_ids or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
