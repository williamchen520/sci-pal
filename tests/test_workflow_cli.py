"""Tests for the workflow CLI (no models, stages injected)."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from services.workflow import StageResult, write_artifact
from services.workflow.run import EXIT_APPROVAL_REQUIRED, EXIT_FAILED, EXIT_OK, load_spec, main


def stage(name, *, status="ok", raises=None, artifact=True):
    def run(context):
        if raises:
            raise raises
        files = []
        if artifact:
            files.append(write_artifact(context, f"{name}.json", {"stage": name}))
        return StageResult(status=status, artifacts=files)

    return run


class LoadSpecTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "job.json"

    def write(self, payload: dict) -> Path:
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        return self.path

    def test_valid_spec(self) -> None:
        path = self.write(
            {
                "topic": "demo",
                "stages": ["plan", "retrieve"],
                "outline": {"sections": [{"title": "Intro"}]},
                "limits": {"max_papers": 5},
            }
        )
        spec = load_spec(path)
        self.assertEqual(spec.topic, "demo")
        self.assertEqual(spec.stages, ("plan", "retrieve"))
        self.assertEqual(spec.metadata["outline"]["sections"][0]["title"], "Intro")
        self.assertEqual(spec.limits["max_papers"], 5)

    def test_missing_topic(self) -> None:
        path = self.write({"stages": ["plan"]})
        with self.assertRaises(ValueError):
            load_spec(path)

    def test_unknown_stage(self) -> None:
        path = self.write({"topic": "demo", "stages": ["plan", "summarize"]})
        with self.assertRaises(ValueError):
            load_spec(path)


class MainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.spec_path = self.dir / "job.json"
        self.run_dir = self.dir / "run"
        self.spec_path.write_text(
            json.dumps({"topic": "demo", "stages": ["plan", "retrieve"]}), encoding="utf-8"
        )

    def argv(self, *extra: str):
        return ["--spec", str(self.spec_path), "--run-dir", str(self.run_dir), *extra]

    def manifest(self) -> dict:
        return json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))

    def test_requires_approval(self) -> None:
        code = main(self.argv(), stages={"plan": stage("plan"), "retrieve": stage("retrieve")})
        self.assertEqual(code, EXIT_APPROVAL_REQUIRED)
        self.assertEqual(self.manifest()["status"], "approval_required")

    def test_approved_run_completes(self) -> None:
        code = main(
            self.argv("--approve"),
            stages={"plan": stage("plan"), "retrieve": stage("retrieve")},
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(self.manifest()["status"], "completed")

    def test_resume_after_approval(self) -> None:
        stages = {"plan": stage("plan"), "retrieve": stage("retrieve")}
        main(self.argv(), stages=stages)
        code = main(self.argv("--approve", "--resume", "--run-id", self.manifest()["run_id"]), stages=stages)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(self.manifest()["status"], "completed")

    def test_failed_stage_exits_1(self) -> None:
        code = main(
            self.argv("--approve"),
            stages={
                "plan": stage("plan"),
                "retrieve": stage("retrieve", raises=RuntimeError("boom")),
            },
        )
        self.assertEqual(code, EXIT_FAILED)
        self.assertEqual(self.manifest()["status"], "failed")

    def test_json_output(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            main(self.argv("--approve", "--json"), stages={"plan": stage("plan"), "retrieve": stage("retrieve")})
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "completed")

    def test_invalid_spec_exits_1(self) -> None:
        self.spec_path.write_text("{}", encoding="utf-8")
        self.assertEqual(main(self.argv()), EXIT_FAILED)


if __name__ == "__main__":
    unittest.main()
