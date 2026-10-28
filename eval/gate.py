"""Compare evaluation results against a baseline (CI gate)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict


def compare(baseline: Dict, current: Dict, tolerance: float = 0.02) -> Dict:
    keys = [key for key in baseline if key.startswith(("recall@", "ndcg@")) or key == "mrr"]
    failures = []
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
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))["summary"]
    current = json.loads(Path(args.current).read_text(encoding="utf-8"))["summary"]
    result = compare(baseline, current, args.tolerance)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
