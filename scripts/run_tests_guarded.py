#!/usr/bin/env python3
"""Run the unit-test suite with the Rule 4 stop-loss guard.

Usage:
    python scripts/run_tests_guarded.py
    python scripts/run_tests_guarded.py --state-file logs/stop_loss_state.json

The same test failing on two consecutive invocations aborts immediately with
"触发止损规则，停止调参，等待人类介入" and exit code 2.
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.quality.stop_loss import StopLossGuard, StopLossTriggered


def iter_tests(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from iter_tests(test)
        else:
            yield test


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-dir", default=str(ROOT / "tests"))
    parser.add_argument("--pattern", default="test_*.py")
    parser.add_argument("--state-file", default=str(ROOT / "logs" / "stop_loss_state.json"))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--verbosity", type=int, default=2)
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.discover(args.start_dir, pattern=args.pattern)
    test_ids = [test.id() for test in iter_tests(suite)]
    result = unittest.TextTestRunner(verbosity=args.verbosity).run(suite)

    failed = {test.id() for test, _ in result.failures + result.errors}
    skipped = {test.id() for test, _ in result.skipped}
    guard = StopLossGuard(args.state_file, limit=args.limit)

    for test_id in test_ids:
        if test_id in skipped:
            continue
        try:
            guard.record_test(test_id, test_id not in failed)
        except StopLossTriggered as exc:
            print(str(exc), flush=True)
            print(f"RULE_VIOLATION: 规则 4 — {test_id} 连续 {exc.count} 次失败", flush=True)
            return 2

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
