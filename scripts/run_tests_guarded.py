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
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SQLITE_MODULES = [
    "test_review_repository",
    "test_reviews_routes",
    "test_systematic_review",
    "test_tasks_routes",
    "test_federated_retriever",
    "test_ingest_tracking_routes",
    "test_sqlite_guard",
]
PG_MODULES = [
    "test_pg_pool",
    "test_pg_schema_v2",
    "test_db_writer_pg_only",
    "test_task_lookup",
    "test_pg_fts",
    "test_pg_vector",
    "test_pg_paragraph_retriever",
    "test_claims_pg_read",
    "test_projects_pg",
    "test_tenancy_pg_writes",
    "test_watch_pg_store",
]
BACKEND_KEYS = [
    "SCIPAL_REVIEWS_BACKEND",
    "SCIPAL_PROJECTS_BACKEND",
    "SCIPAL_EXPERIMENTS_BACKEND",
    "SCIPAL_CLAIMS_BACKEND",
    "SCIPAL_TASKS_BACKEND",
    "SCIPAL_SYSTEMATIC_BACKEND",
    "SCIPAL_WATCH_PG_STORE",
    "SCIPAL_NOTES_BACKEND",
]

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
    parser.add_argument("--group", choices=["sqlite", "pg"], default=None)
    args = parser.parse_args()

    if args.group:
        for key in BACKEND_KEYS:
            os.environ.pop(key, None)
        if args.group == "sqlite":
            modules = SQLITE_MODULES
        else:
            modules = PG_MODULES
            for key in BACKEND_KEYS:
                os.environ[key] = "postgres"
        suite = unittest.TestSuite(
            unittest.defaultTestLoader.loadTestsFromName(f"tests.{name}") for name in modules
        )
    else:
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
