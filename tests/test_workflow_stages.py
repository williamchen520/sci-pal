"""Tests for the model-free workflow stages (plan / store / export)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.workflow import StageResult, WorkflowSpec, run_workflow
from services.workflow.stages import (
    build_export_stage,
    build_plan_stage,
    build_retrieve_stage,
    build_store_stage,
)
from services.workflow.types import StageContext


def context(run_dir: Path, spec: WorkflowSpec, run_id: str = "r1") -> StageContext:
    run_dir.mkdir(parents=True, exist_ok=True)
    return StageContext(run_id=run_id, run_dir=run_dir, spec=spec, services={}, logger=None)


class PlanStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spec(self, outline) -> WorkflowSpec:
        return WorkflowSpec(
            topic="demo", stages=("plan", "store", "export"), metadata={"outline": outline}
        )

    def test_writes_plan_with_normalized_sections(self) -> None:
        spec = self.spec(
            {
                "sections": [
                    {"title": "Intro", "keywords": "a, b，c"},
                    {"id": "s2", "name": "Methods"},
                    {"title": "   "},
                ]
            }
        )
        result = build_plan_stage()(context(self.dir, spec))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.metrics["sections"], 2)
        plan = json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["sections"][0]["id"], "sec-01")
        self.assertEqual(plan["sections"][0]["keywords"], ["a", "b", "c"])
        self.assertEqual(plan["sections"][1]["id"], "s2")
        self.assertEqual(plan["run_id"], "r1")

    def test_missing_outline_fails_with_invalid_input(self) -> None:
        result = build_plan_stage()(context(self.dir, self.spec({})))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "invalid_input")


class StoreStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_missing_review_fails(self) -> None:
        spec = WorkflowSpec(topic="demo", stages=("plan", "store", "export"))
        result = build_store_stage()(context(self.dir, spec))
        self.assertEqual(result.status, "failed")
        self.assertIn("review.json", result.errors[0]["message"])

    def test_default_store_writes_record(self) -> None:
        spec = WorkflowSpec(topic="demo", stages=("plan", "store", "export"))
        (self.dir / "review.json").write_text('{"topic": "demo", "sections": []}', encoding="utf-8")
        result = build_store_stage()(context(self.dir, spec))
        self.assertEqual(result.status, "ok")
        record = json.loads((self.dir / "store.json").read_text(encoding="utf-8"))
        self.assertTrue(record["review_id"].startswith("rev_"))
        self.assertEqual(record["topic"], "demo")

    def test_injected_store_is_used(self) -> None:
        seen = {}

        def saver(review, ctx):
            seen["review"] = review
            return {"review_id": "rev_custom", "topic": review["topic"]}

        spec = WorkflowSpec(topic="demo", stages=("store",))
        (self.dir / "review.json").write_text('{"topic": "x"}', encoding="utf-8")
        result = build_store_stage(saver)(context(self.dir, spec))
        self.assertEqual(result.metrics["review_id"], "rev_custom")
        self.assertEqual(seen["review"]["topic"], "x")


class ExportStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_default_export_copies_markdown(self) -> None:
        spec = WorkflowSpec(topic="demo", stages=("export",))
        (self.dir / "store.json").write_text('{"review_id": "rev_1"}', encoding="utf-8")
        (self.dir / "draft.md").write_text("# review body", encoding="utf-8")
        result = build_export_stage()(context(self.dir, spec))
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            (self.dir / "exports" / "review.md").read_text(encoding="utf-8"), "# review body"
        )
        metadata = json.loads((self.dir / "exports" / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["review_id"], "rev_1")

    def test_missing_store_fails(self) -> None:
        spec = WorkflowSpec(topic="demo", stages=("export",))
        result = build_export_stage()(context(self.dir, spec))
        self.assertEqual(result.status, "failed")
        self.assertIn("store.json", result.errors[0]["message"])


class RetrieveStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spec(self, max_papers=25) -> WorkflowSpec:
        return WorkflowSpec(
            topic="demo",
            stages=("plan", "retrieve", "store", "export"),
            limits={"max_papers": max_papers},
        )

    def test_missing_plan_fails(self) -> None:
        result = build_retrieve_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "invalid_input")

    def test_empty_sections_fail(self) -> None:
        (self.dir / "plan.json").write_text('{"sections": []}', encoding="utf-8")
        result = build_retrieve_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")

    def test_injected_finder_receives_plan_and_writes_artifact(self) -> None:
        (self.dir / "plan.json").write_text(
            '{"sections": [{"id": "sec-01", "title": "Intro", "keywords": []}]}',
            encoding="utf-8",
        )
        seen = {}

        def finder(sections, topic, max_papers, ctx):
            seen.update(sections=sections, topic=topic, max_papers=max_papers)
            return {"sections": sections, "papers": [{"paper_id": "p1"}, {"paper_id": "p2"}]}

        result = build_retrieve_stage(finder)(context(self.dir, self.spec(max_papers=25)))
        self.assertEqual(result.status, "ok")
        self.assertEqual(seen["topic"], "demo")
        self.assertEqual(seen["max_papers"], 25)
        self.assertEqual(result.metrics, {"sections": 1, "papers": 2})
        payload = json.loads((self.dir / "retrieve.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["papers"]), 2)

    def test_finder_error_is_reported_as_upstream(self) -> None:
        (self.dir / "plan.json").write_text(
            '{"sections": [{"id": "s1", "title": "Intro"}]}', encoding="utf-8"
        )

        def boom(*args, **kwargs):
            raise RuntimeError("retriever unavailable")

        result = build_retrieve_stage(boom)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "upstream")
        self.assertIn("retriever unavailable", result.errors[0]["message"])


class EndToEndTests(unittest.TestCase):
    def test_plan_store_export_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "r1"
            run_dir.mkdir(parents=True)
            (run_dir / "review.json").write_text('{"topic": "demo"}', encoding="utf-8")
            (run_dir / "draft.md").write_text("# draft", encoding="utf-8")

            spec = WorkflowSpec(
                topic="demo",
                stages=("plan", "store", "export"),
                metadata={"outline": {"sections": [{"title": "Intro"}]}},
            )
            stages = {
                "plan": build_plan_stage(),
                "store": build_store_stage(),
                "export": build_export_stage(),
            }
            manifest = run_workflow(
                spec, stages, run_dir=run_dir, approve=True, run_id="r1"
            )

            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(
                manifest["artifacts"], ["plan.json", "store.json", "exports/review.md", "exports/metadata.json"]
            )
            self.assertTrue((run_dir / "exports" / "review.md").exists())


if __name__ == "__main__":
    unittest.main()
