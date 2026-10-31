#!/usr/bin/env python3
"""Record one dataset metric and enforce Rule 4's two-strike stop-loss.

Usage:
    python scripts/record_eval_metric.py --name Recall@10 --value 0.5885
    python scripts/record_eval_metric.py --name loss --value 0.42 --direction min

Exit codes:
    0  recorded (first baseline, improvement, or first non-improvement)
    2  stop-loss triggered; stop tuning and wait for a human
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.quality.stop_loss import StopLossGuard, StopLossTriggered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--value", required=True, type=float)
    parser.add_argument("--direction", choices=["max", "min"], default="max")
    parser.add_argument("--tolerance", type=float, default=0.0)
    parser.add_argument("--state-file", default=str(ROOT / "logs" / "stop_loss_state.json"))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--reset", action="store_true", help="clear state instead of recording")
    args = parser.parse_args()

    guard = StopLossGuard(args.state_file, limit=args.limit)
    if args.reset:
        guard.reset()
        print("stop-loss state cleared")
        return 0
    try:
        count = guard.record_metric(
            args.name,
            args.value,
            direction=args.direction,
            tolerance=args.tolerance,
        )
    except StopLossTriggered as exc:
        print(str(exc), flush=True)
        print(f"RULE_VIOLATION: 规则 4 — {args.name} 连续 {exc.count} 次未提升", flush=True)
        return 2

    print(f"{args.name}={args.value} recorded; consecutive_non_improvements={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
