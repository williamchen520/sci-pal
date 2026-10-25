"""Tests for the model-free workflow stages (plan / store / export)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.workflow import StageResult, WorkflowSpec, run_workflow
from services.workflow.stages import (
    build_draft_stage,
    build_evidence_stage,
    build_export_stage,
    build_plan_stage,
    build_retrieve_stage,
    build_store_stage,
    build_verify_stage,
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

    def test_default_store_persists_into_review_store(self) -> None:
        from unittest.mock import patch

        captured = {}

        class FakeStore:
            def store(self, output, draft, cards):
                captured.update(output=output, draft=draft, cards=cards)
                return "rev_fake"

        spec = WorkflowSpec(topic="demo", stages=("store",))
        (self.dir / "plan.json").write_text(
            '{"sections": [{"id": "sec-01", "title": "Intro"}]}', encoding="utf-8"
        )
        (self.dir / "review.json").write_text(
            json.dumps(
                {
                    "topic": "demo",
                    "markdown": "# md",
                    "sentences": [
                        {"sentence_id": "s1", "section_id": "sec-01", "text": "claim [ev1]", "evidence_ids": ["ev1"]}
                    ],
                    "evidence_cards": {
                        "ev1": {"evidence_id": "ev1", "paper_id": "p1", "para_id": "a1", "content": "c"}
                    },
                }
            ),
            encoding="utf-8",
        )
        ctx = context(self.dir, spec)
        ctx.services = {"db_path": self.dir / "reviews.db"}
        with patch("services.review.review_store.get_review_store", return_value=FakeStore()):
            result = build_store_stage()(ctx)

        self.assertEqual(result.status, "ok", result.errors)
        self.assertEqual(result.metrics["review_id"], "rev_fake")
        self.assertEqual(captured["output"].markdown, "# md")
        self.assertEqual(len(captured["draft"].sentences), 1)
        self.assertEqual(len(captured["cards"]), 1)

        from services.review.review_repository import ReviewRepository

        record = ReviewRepository(self.dir / "reviews.db").get("rev_fake")
        self.assertIsNotNone(record)
        self.assertEqual(record["markdown"], "# md")
        self.assertEqual(record["run_id"], "r1")
        self.assertEqual(record["stats"]["total_sentences"], 1)

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


class VerifyStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spec(self) -> WorkflowSpec:
        return WorkflowSpec(topic="demo", stages=("plan", "retrieve", "verify", "store", "export"))

    def write_review(self, payload: dict) -> None:
        (self.dir / "review.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_missing_review_fails(self) -> None:
        result = build_verify_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertIn("review.json", result.errors[0]["message"])

    def test_injected_checker_writes_metrics(self) -> None:
        self.write_review({"topic": "demo", "sentences": [], "evidence_cards": {}})

        def checker(review, ctx):
            return {"stats": {"total_sentences": 2, "verified": 1, "rejected": 1, "pass_rate": 0.5}}

        result = build_verify_stage(checker)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.metrics["verified"], 1)
        self.assertTrue((self.dir / "verify.json").exists())

    def test_checker_error_is_reported(self) -> None:
        self.write_review({"topic": "demo"})

        def boom(review, ctx):
            raise RuntimeError("verifier exploded")

        result = build_verify_stage(boom)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "internal")

    def test_default_adapter_uses_citation_verifier(self) -> None:
        (self.dir / "plan.json").write_text(
            '{"sections": [{"id": "sec-01", "title": "Intro"}]}', encoding="utf-8"
        )
        self.write_review(
            {
                "topic": "demo",
                "sentences": [
                    {"sentence_id": "s1", "section_id": "sec-01", "text": "A finding [1].", "evidence_ids": ["ev1"]},
                    {"sentence_id": "s2", "section_id": "sec-01", "text": "Unsupported claim.", "evidence_ids": []},
                ],
                "evidence_cards": {
                    "ev1": {
                        "evidence_id": "ev1",
                        "paper_id": "p1",
                        "para_id": "para1",
                        "content": "finding",
                    }
                },
            }
        )
        result = build_verify_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok", result.errors)
        self.assertEqual(result.metrics["total_sentences"], 2)
        self.assertEqual(result.metrics["verified"], 1)
        self.assertEqual(result.metrics["rejected"], 1)


class EvidenceStageTests(unittest.TestCase):
    LONG_TEXT = "This paragraph reports that treatment reduced mortality by twenty percent in the cohort."

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spec(self) -> WorkflowSpec:
        return WorkflowSpec(topic="demo", stages=("plan", "retrieve", "evidence"))

    def write_retrieve(self, payload: dict) -> None:
        (self.dir / "retrieve.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_retrieve_cards_are_used_without_extraction(self) -> None:
        self.write_retrieve(
            {
                "evidence_cards": [
                    {"evidence_id": "ev1", "paper_id": "p1", "para_id": "a1", "content": "c"}
                ]
            }
        )
        calls = []

        def extractor(payload, ctx):
            calls.append(payload)
            return {"cards": [], "count": 0}

        result = build_evidence_stage(extractor)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.metrics["cards"], 1)
        self.assertEqual(calls, [])

    def test_missing_retrieve_fails(self) -> None:
        result = build_evidence_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertIn("retrieve.json", result.errors[0]["message"])

    def test_injected_extractor_used(self) -> None:
        self.write_retrieve({"paragraphs": [{"paper_id": "p1", "para_id": "a", "text": "x"}]})
        seen = {}

        def extractor(payload, ctx):
            seen["payload"] = payload
            return {"cards": [{"evidence_id": "ev1"}], "count": 1}

        result = build_evidence_stage(extractor)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.metrics["cards"], 1)
        self.assertIn("paragraphs", seen["payload"])

    def test_no_source_text_fails(self) -> None:
        self.write_retrieve({"papers": [{"paper_id": "p1", "title": "no abstract"}]})
        result = build_evidence_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "invalid_input")

    def test_default_extractor_builds_cards(self) -> None:
        self.write_retrieve(
            {
                "paragraphs": [
                    {"paper_id": "p1", "para_id": "a1", "text": self.LONG_TEXT, "paper_title": "T1"},
                    {"paper_id": "p1", "para_id": "a1", "text": self.LONG_TEXT},  # duplicate para
                    {"paper_id": "p2", "para_id": "a2", "text": "too short"},
                ]
            }
        )
        result = build_evidence_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok", result.errors)
        self.assertEqual(result.metrics["cards"], 1)  # deduped + short dropped
        payload = json.loads((self.dir / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["cards"][0]["paper_id"], "p1")

    def test_abstracts_fallback(self) -> None:
        self.write_retrieve(
            {"papers": [{"paper_id": "p9", "title": "T9", "abstract": self.LONG_TEXT}]}
        )
        result = build_evidence_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok", result.errors)
        payload = json.loads((self.dir / "evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["cards"][0]["para_id"], "p9::abstract")
        self.assertEqual(payload["cards"][0]["source_type"], "abstract")


class FakeReviewGenerator:
    """Stands in for ReviewGenerator: returns a prebuilt ReviewDraft."""

    def __init__(self, draft):
        self.draft = draft
        self.calls = []

    def _write_draft(self, topic, outline, cards, review_type="narrative", language="en"):
        self.calls.append(
            {"topic": topic, "outline": outline, "cards": cards, "review_type": review_type}
        )
        return self.draft


def make_review_draft(section_count: int = 1):
    from services.review.models import (
        EvidenceCard,
        ReviewDraft,
        ReviewOutline,
        ReviewSection,
        ReviewSentence,
    )

    card = EvidenceCard(
        evidence_id="ev1", paper_id="p1", para_id="a1", content="finding"
    )
    sections = [
        ReviewSection(
            section_id=f"sec-0{index}",
            title=f"Section {index}",
            order=index,
            assigned_evidence_ids=["ev1"],
        )
        for index in range(1, section_count + 1)
    ]
    sentences = [
        ReviewSentence(
            sentence_id=f"s{index}",
            section_id=f"sec-0{index}",
            text=f"Claim {index} [ev1].",
            evidence_ids=["ev1"],
        )
        for index in range(1, section_count + 1)
    ]
    return ReviewDraft(
        topic="demo",
        outline=ReviewOutline(topic="demo", sections=sections),
        sentences=sentences,
        evidence_cards={"ev1": card},
    )


class DraftStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def spec(self) -> WorkflowSpec:
        return WorkflowSpec(topic="demo", stages=("plan", "retrieve", "evidence", "draft"))

    def write_plan(self, sections=None) -> None:
        sections = sections or [{"id": "sec-01", "title": "Intro", "keywords": []}]
        (self.dir / "plan.json").write_text(
            json.dumps({"sections": sections}), encoding="utf-8"
        )

    def write_evidence(self, cards=None) -> None:
        cards = cards or [
            {"evidence_id": "ev1", "paper_id": "p1", "para_id": "a1", "content": "finding"}
        ]
        (self.dir / "evidence.json").write_text(
            json.dumps({"cards": cards}), encoding="utf-8"
        )

    def test_missing_plan(self) -> None:
        result = build_draft_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertIn("plan.json", result.errors[0]["message"])

    def test_missing_evidence(self) -> None:
        self.write_plan()
        result = build_draft_stage()(context(self.dir, self.spec()))
        self.assertEqual(result.status, "failed")
        self.assertIn("evidence.json", result.errors[0]["message"])

    def test_references_are_derived_from_cards(self) -> None:
        self.write_plan()
        self.write_evidence(
            [
                {"evidence_id": "ev1", "paper_id": "p1", "para_id": "a1", "content": "c1", "paper_title": "T1"},
                {"evidence_id": "ev2", "paper_id": "p1", "para_id": "a2", "content": "c2", "paper_title": "T1"},
                {"evidence_id": "ev3", "paper_id": "p2", "para_id": "a3", "content": "c3", "paper_title": "T2"},
            ]
        )

        def writer(plan, evidence, ctx):
            return {
                "topic": "demo",
                "sections": [],
                "sentences": [],
                "evidence_cards": {card["evidence_id"]: card for card in evidence["cards"]},
                "markdown": "# md",
            }

        result = build_draft_stage(writer)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok", result.errors)
        review = json.loads((self.dir / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(len(review["references"]), 2)
        self.assertEqual({ref["paper_id"] for ref in review["references"]}, {"p1", "p2"})
        self.assertEqual(result.metrics["references"], 2)

    def test_references_enriched_from_papers_table(self) -> None:
        self.write_plan()
        self.write_evidence(
            [{"evidence_id": "ev1", "paper_id": "p1", "para_id": "a1", "content": "c"}]
        )
        db = self.dir / "meta.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT, title TEXT, authors TEXT, journal TEXT, year INTEGER, doi TEXT)"
        )
        conn.execute(
            "INSERT INTO papers VALUES ('p1', 'Real Title', 'A, B', 'Nature', 2024, '10.1/x')"
        )
        conn.commit()
        conn.close()

        def writer(plan, evidence, ctx):
            return {
                "topic": "demo",
                "sections": [],
                "sentences": [],
                "evidence_cards": {"ev1": evidence["cards"][0]},
                "markdown": "",
            }

        ctx = context(self.dir, self.spec())
        ctx.services = {"db_path": db}
        result = build_draft_stage(writer)(ctx)
        self.assertEqual(result.status, "ok", result.errors)
        review = json.loads((self.dir / "review.json").read_text(encoding="utf-8"))
        ref = review["references"][0]
        self.assertEqual(ref["title"], "Real Title")
        self.assertEqual(ref["journal"], "Nature")
        self.assertEqual(ref["year"], 2024)

    def test_injected_writer_produces_artifacts(self) -> None:
        self.write_plan()
        self.write_evidence()

        def writer(plan, evidence, ctx):
            return {
                "topic": "demo",
                "sections": [{"section_id": "sec-01", "title": "Intro"}],
                "sentences": [{"sentence_id": "s1", "section_id": "sec-01", "text": "Claim [ev1].", "evidence_ids": ["ev1"]}],
                "evidence_cards": {"ev1": evidence["cards"][0]},
                "markdown": "# demo\n\n## Intro\nClaim [ev1].\n",
            }

        result = build_draft_stage(writer)(context(self.dir, self.spec()))
        self.assertEqual(result.status, "ok", result.errors)
        self.assertEqual(result.metrics["sentences"], 1)
        self.assertTrue((self.dir / "review.json").exists())
        self.assertIn("## Intro", (self.dir / "draft.md").read_text(encoding="utf-8"))

    def test_default_writer_serializes_review_draft(self) -> None:
        self.write_plan()
        self.write_evidence()
        generator = FakeReviewGenerator(make_review_draft(1))
        ctx = context(self.dir, self.spec())
        ctx.services = {"generator": generator}

        result = build_draft_stage()(ctx)
        self.assertEqual(result.status, "ok", result.errors)
        review = json.loads((self.dir / "review.json").read_text(encoding="utf-8"))
        self.assertEqual(review["topic"], "demo")
        self.assertEqual(len(review["sentences"]), 1)
        self.assertIn("ev1", review["evidence_cards"])
        self.assertIn("## Section 1", (self.dir / "draft.md").read_text(encoding="utf-8"))

    def test_multi_section_without_assignment_fails(self) -> None:
        self.write_plan(
            [
                {"id": "sec-01", "title": "Intro"},
                {"id": "sec-02", "title": "Methods"},
            ]
        )
        self.write_evidence()
        ctx = context(self.dir, self.spec())
        ctx.services = {"generator": FakeReviewGenerator(make_review_draft(2))}
        result = build_draft_stage()(ctx)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.errors[0]["kind"], "invalid_input")

    def test_assignments_from_retrieve_are_used(self) -> None:
        self.write_plan(
            [
                {"id": "sec-01", "title": "Intro"},
                {"id": "sec-02", "title": "Methods"},
            ]
        )
        self.write_evidence()
        (self.dir / "retrieve.json").write_text(
            json.dumps(
                {
                    "sections": [
                        {"id": "sec-01", "assigned_evidence_ids": ["ev1"]},
                        {"id": "sec-02", "assigned_evidence_ids": ["ev1"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        generator = FakeReviewGenerator(make_review_draft(2))
        ctx = context(self.dir, self.spec())
        ctx.services = {"generator": generator}
        result = build_draft_stage()(ctx)
        self.assertEqual(result.status, "ok", result.errors)
        self.assertEqual(len(generator.calls[0]["outline"].sections), 2)


class FullPipelineTests(unittest.TestCase):
    def test_full_pipeline_without_models(self) -> None:
        """plan -> retrieve -> evidence -> draft -> verify -> store -> export."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "runs" / "r1"

            spec = WorkflowSpec(
                topic="demo",
                stages=("plan", "retrieve", "evidence", "draft", "verify", "store", "export"),
                limits={"max_papers": 10},
                metadata={"outline": {"sections": [{"id": "sec-01", "title": "Intro"}]}},
            )

            def retrieve(sections, topic, max_papers, ctx):
                return {
                    "sections": [
                        {"id": "sec-01", "assigned_evidence_ids": ["ev1"]}
                    ],
                    "paragraphs": [
                        {
                            "paper_id": "p1",
                            "para_id": "a1",
                            "text": "Treatment reduced mortality by twenty percent in the trial cohort.",
                        }
                    ],
                    "papers": [],
                }

            def draft(plan, evidence, ctx):
                card = next(iter(evidence["cards"]))
                return {
                    "topic": "demo",
                    "sections": [{"section_id": "sec-01", "title": "Intro"}],
                    "sentences": [
                        {
                            "sentence_id": "s1",
                            "section_id": "sec-01",
                            "text": "Treatment reduced mortality [ev1].",
                            "evidence_ids": [card["evidence_id"]],
                        }
                    ],
                    "evidence_cards": {card["evidence_id"]: card},
                    "markdown": "# demo\n\n## Intro\nTreatment reduced mortality [ev1].\n",
                }

            stages = {
                "plan": build_plan_stage(),
                "retrieve": build_retrieve_stage(retrieve),
                "evidence": build_evidence_stage(),
                "draft": build_draft_stage(draft),
                "verify": build_verify_stage(),
                "store": build_store_stage(),
                "export": build_export_stage(),
            }

            manifest = run_workflow(spec, stages, run_dir=run_dir, approve=True, run_id="r1")
            self.assertEqual(manifest["status"], "completed", manifest.get("errors"))
            self.assertEqual(
                [stage["status"] for stage in manifest["stages"]],
                ["ok"] * 7,
            )
            verify = json.loads((run_dir / "verify.json").read_text(encoding="utf-8"))
            self.assertEqual(verify["stats"]["verified"], 1)
            self.assertTrue((run_dir / "exports" / "review.md").exists())


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
