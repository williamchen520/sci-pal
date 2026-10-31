"""Rule 4 stop-loss guard tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.quality.stop_loss import STOP_MESSAGE, StopLossGuard, StopLossTriggered


class StopLossGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state.json"

    def test_same_test_fails_twice_triggers(self) -> None:
        guard = StopLossGuard(self.state)
        guard.record_test("tests.test_x.Case.test_a", False)
        with self.assertRaises(StopLossTriggered) as ctx:
            guard.record_test("tests.test_x.Case.test_a", False)
        self.assertIn(STOP_MESSAGE, str(ctx.exception))

    def test_pass_resets_failure_counter(self) -> None:
        guard = StopLossGuard(self.state)
        guard.record_test("test_a", False)
        guard.record_test("test_a", True)
        self.assertEqual(guard.record_test("test_a", False), 1)

    def test_metric_baseline_then_two_non_improvements(self) -> None:
        guard = StopLossGuard(self.state)
        self.assertEqual(guard.record_metric("Recall@10", 0.60), 0)
        self.assertEqual(guard.record_metric("Recall@10", 0.60), 1)
        with self.assertRaises(StopLossTriggered):
            guard.record_metric("Recall@10", 0.59)

    def test_metric_improvement_resets(self) -> None:
        guard = StopLossGuard(self.state)
        guard.record_metric("Recall@10", 0.60)
        guard.record_metric("Recall@10", 0.59)
        guard.record_metric("Recall@10", 0.61)
        guard.record_metric("Recall@10", 0.61)

    def test_state_persists_across_instances(self) -> None:
        StopLossGuard(self.state).record_test("test_a", False)
        with self.assertRaises(StopLossTriggered):
            StopLossGuard(self.state).record_test("test_a", False)

    def test_lower_is_better_metric(self) -> None:
        guard = StopLossGuard(self.state)
        guard.record_metric("loss", 0.5, direction="min")
        guard.record_metric("loss", 0.5, direction="min")
        with self.assertRaises(StopLossTriggered):
            guard.record_metric("loss", 0.6, direction="min")


if __name__ == "__main__":
    unittest.main()
