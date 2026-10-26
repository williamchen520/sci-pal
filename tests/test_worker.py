"""Tests for the resident workflow worker."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.workflow.worker import process_once


class WorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / "queue"
        self.queue.mkdir()
        self.spec = self.root / "job.json"
        self.spec.write_text('{"topic": "demo"}', encoding="utf-8")

    def _enqueue(self, name: str, run_dir: Path) -> Path:
        job = self.queue / f"{name}.job.json"
        job.write_text(
            json.dumps({"spec": str(self.spec), "run_dir": str(run_dir), "approve": True}),
            encoding="utf-8",
        )
        return job

    def test_processes_job_and_records_result(self) -> None:
        run_dir = self.root / "run1"
        job = self._enqueue("a", run_dir)

        def fake_runner(spec, stages, *, run_dir, approve):
            return {"status": "completed", "run_id": "r1"}

        handled = process_once(self.queue, runner=fake_runner, stages={}, log=lambda _: None)
        self.assertEqual(handled, 1)
        self.assertFalse(job.exists())

        result = json.loads((self.queue / "processed" / "a.job.json.result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["run_id"], "r1")

    def test_runner_failure_is_recorded(self) -> None:
        def failing_runner(spec, stages, *, run_dir, approve):
            raise ValueError("boom")

        self._enqueue("b", self.root / "run2")
        handled = process_once(self.queue, runner=failing_runner, stages={}, log=lambda _: None)
        self.assertEqual(handled, 1)

        result = json.loads((self.queue / "processed" / "b.job.json.result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("boom", result["error"])

    def test_empty_queue_is_a_noop(self) -> None:
        self.assertEqual(process_once(self.queue, runner=None, stages={}, log=lambda _: None), 0)


if __name__ == "__main__":
    unittest.main()
