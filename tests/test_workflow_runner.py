"""Tests for the workflow state machine (no models, no database)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.workflow import StageResult, WorkflowSpec, run_workflow, write_artifact


def make_stage(name: str, calls: dict, *, status: str = "ok", artifacts=None, raises=None):
    def stage(context):
        calls[name] = calls.get(name, 0) + 1
        if raises:
            raise raises
        files = []
        for artifact in artifacts or []:
            files.append(write_artifact(context, artifact, {"stage": name}))
        return StageResult(status=status, artifacts=files, metrics={"n": 1})

    return stage


class WorkflowRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "runs" / "r1"
        self.calls: dict[str, int] = {}

    def spec(self, stages=("plan", "retrieve", "store")):
        return WorkflowSpec(topic="demo", stages=stages)

    def stages(self, **overrides):
        base = {name: make_stage(name, self.calls, artifacts=[f"{name}.json"]) for name in self.spec().stages}
        base.update(overrides)
        return base

    def manifest(self) -> dict:
        return json.loads((self.dir / "run.json").read_text(encoding="utf-8"))

    def test_happy_path(self) -> None:
        result = run_workflow(
            self.spec(), self.stages(), run_dir=self.dir, approve=True, run_id="r1"
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["run_id"], "r1")
        self.assertEqual([s["status"] for s in result["stages"]], ["ok", "ok", "ok"])
        self.assertEqual(result["artifacts"], ["plan.json", "retrieve.json", "store.json"])
        self.assertIsNotNone(result["completed_at"])
        self.assertTrue((self.dir / "run.json").exists())

    def test_approval_gate_blocks_after_plan(self) -> None:
        result = run_workflow(self.spec(), self.stages(), run_dir=self.dir, approve=False)
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(self.calls, {"plan": 1})
        self.assertEqual(result["stages"][1]["status"], "pending")

    def test_approval_can_be_granted_on_resume(self) -> None:
        run_workflow(self.spec(), self.stages(), run_dir=self.dir, approve=False, run_id="r1")
        result = run_workflow(
            self.spec(), self.stages(), run_dir=self.dir, approve=True, run_id="r1", resume=True
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.calls["plan"], 1)  # not re-run
        self.assertIn("retrieve", self.calls)

    def test_skipped_stage_marks_partial_completion(self) -> None:
        stages = self.stages(store=make_stage("store", self.calls, status="skipped"))
        result = run_workflow(self.spec(), stages, run_dir=self.dir, approve=True)
        self.assertEqual(result["status"], "completed_with_skips")
        self.assertEqual(result["stages"][2]["status"], "skipped")

    def test_failure_stops_and_persists(self) -> None:
        stages = self.stages(retrieve=make_stage("retrieve", self.calls, raises=RuntimeError("boom")))
        result = run_workflow(self.spec(), stages, run_dir=self.dir, approve=True)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("store", self.calls)
        self.assertEqual(result["errors"][0]["stage"], "retrieve")
        self.assertEqual(result["errors"][0]["kind"], "internal")
        self.assertEqual(self.manifest()["status"], "failed")

    def test_continue_on_error_runs_remaining_stages(self) -> None:
        spec = WorkflowSpec(topic="demo", stages=("plan", "retrieve", "store"), limits={"continue_on_error": True})
        stages = self.stages(retrieve=make_stage("retrieve", self.calls, raises=RuntimeError("boom")))
        result = run_workflow(spec, stages, run_dir=self.dir, approve=True)
        self.assertEqual(result["status"], "completed_with_skips")
        self.assertIn("store", self.calls)
        self.assertEqual(result["stages"][1]["status"], "failed")

    def test_resume_skips_completed_stages(self) -> None:
        spec = self.spec()
        first = {
            "plan": make_stage("plan", self.calls, artifacts=["plan.json"]),
            "retrieve": make_stage("retrieve", self.calls, raises=RuntimeError("boom")),
            "store": make_stage("store", self.calls, artifacts=["store.json"]),
        }
        run_workflow(spec, first, run_dir=self.dir, approve=True, run_id="r1")
        second = {
            "plan": make_stage("plan", self.calls, artifacts=["plan.json"]),
            "retrieve": make_stage("retrieve", self.calls, artifacts=["retrieve.json"]),
            "store": make_stage("store", self.calls, artifacts=["store.json"]),
        }
        result = run_workflow(spec, second, run_dir=self.dir, approve=True, run_id="r1", resume=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.calls["plan"], 1)
        self.assertEqual(self.calls["retrieve"], 2)

    def test_refuses_existing_run_without_resume(self) -> None:
        self.dir.mkdir(parents=True)
        (self.dir / "run.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            run_workflow(self.spec(), self.stages(), run_dir=self.dir, approve=True)

    def test_resume_without_manifest_fails(self) -> None:
        with self.assertRaises(FileNotFoundError):
            run_workflow(self.spec(), self.stages(), run_dir=self.dir, resume=True)

    def test_missing_stage_implementation(self) -> None:
        with self.assertRaises(ValueError):
            run_workflow(self.spec(), {"plan": make_stage("plan", self.calls)}, run_dir=self.dir)

    def test_unknown_stage_name(self) -> None:
        with self.assertRaises(ValueError):
            WorkflowSpec(topic="demo", stages=("plan", "summarize"))

    def test_no_temp_files_left_behind(self) -> None:
        run_workflow(self.spec(), self.stages(), run_dir=self.dir, approve=True)
        leftovers = [p.name for p in self.dir.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_write_artifact_text_and_json(self) -> None:
        from services.workflow.types import StageContext

        context = StageContext(
            run_id="r1", run_dir=self.dir, spec=self.spec(), services={}, logger=None
        )
        self.dir.mkdir(parents=True, exist_ok=True)
        write_artifact(context, "note.md", "# hi")
        write_artifact(context, "data.json", {"a": 1})
        self.assertEqual((self.dir / "note.md").read_text(encoding="utf-8"), "# hi")
        self.assertEqual(json.loads((self.dir / "data.json").read_text(encoding="utf-8")), {"a": 1})


if __name__ == "__main__":
    unittest.main()
