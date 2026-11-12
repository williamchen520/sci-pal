"""Paired bootstrap for Phase C arm differences (Hit@10)."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def hit10(row: dict) -> int:
    rank = row.get("first_rank")
    return int(rank is not None and rank <= 10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--baseline", default="F0")
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    arms = data["arms"]
    base_rows = {row["claim_id"]: row for row in arms[args.baseline]["metrics"]["rows"]}
    rng = random.Random(args.seed)
    result = {"baseline": args.baseline, "metric": "hit@10", "samples": args.samples, "comparisons": {}}
    for arm, payload in arms.items():
        if arm == args.baseline:
            continue
        rows = {row["claim_id"]: row for row in payload["metrics"]["rows"]}
        common = sorted(set(base_rows) & set(rows))
        diffs = [hit10(rows[key]) - hit10(base_rows[key]) for key in common]
        observed = sum(diffs) / len(diffs)
        boot = []
        for _ in range(args.samples):
            sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
            boot.append(sum(sample) / len(sample))
        boot.sort()
        lo = boot[int(0.025 * len(boot))]
        hi = boot[int(0.975 * len(boot)) - 1]
        result["comparisons"][arm] = {
            "n": len(common),
            "diff": observed,
            "ci95": [lo, hi],
            "p_one_sided": sum(value <= 0 for value in boot) / len(boot),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
