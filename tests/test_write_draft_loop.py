"""Integration test: ``_write_draft`` now delegates the retry loop to section_loop."""

from __future__ import annotations

import unittest

from services.review.models import EvidenceCard, ReviewOutline, ReviewSection, ReviewSentence
from services.review.review_generator import ReviewGenerator


def make_card(evidence_id: str) -> EvidenceCard:
    return EvidenceCard(
        evidence_id=evidence_id, paper_id="p1", para_id=f"a_{evidence_id}", content="finding"
    )


class FakeDraftGenerator:
    """Generator with only the methods ``_write_draft`` touches."""

    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.feedbacks: list[str] = []
        self._auto_cite_count = 0
        self._insufficient_evidence_sections: list[str] = []

    def _write_section(self, section, evidence, **kwargs) -> str:
        feedback = kwargs.get("feedback", "")
        self.feedbacks.append(feedback)
        return "first text" if not feedback else "revised text"

    def _review_section(self, section, text, evidence, language="en"):
        return self.scores.pop(0), "add more citations"

    def _split_and_link(self, text, section_id, evidence, offset):
        return [
            ReviewSentence(
                sentence_id=f"sent_{section_id}_{offset}",
                section_id=section_id,
                text=text,
                evidence_ids=[card.evidence_id for card in evidence],
            )
        ]

    def _auto_cite_sentences(self, sentences, evidence):
        return 0

    def _generate_fallback_section(self, *args, **kwargs):
        raise AssertionError("fallback should not run when evidence is sufficient")


def run_draft(gen, section_count: int = 1):
    section = ReviewSection(
        section_id="s1",
        title="Introduction",
        assigned_evidence_ids=["ev1", "ev2"],
    )
    outline = ReviewOutline(topic="demo", sections=[section])
    evidence = {"ev1": make_card("ev1"), "ev2": make_card("ev2")}
    return ReviewGenerator._write_draft(gen, "demo", outline, evidence)


class WriteDraftLoopTests(unittest.TestCase):
    def test_revision_is_accepted_when_it_scores_better(self) -> None:
        gen = FakeDraftGenerator([40.0, 85.0])
        draft = run_draft(gen)
        self.assertEqual(draft.sentences[0].text, "revised text")
        self.assertEqual(gen.feedbacks, ["", "add more citations"])

    def test_worse_revision_is_rejected(self) -> None:
        gen = FakeDraftGenerator([40.0, 30.0])
        draft = run_draft(gen)
        self.assertEqual(draft.sentences[0].text, "first text")
        self.assertEqual(len(gen.feedbacks), 2)

    def test_passing_first_draft_is_not_revised(self) -> None:
        gen = FakeDraftGenerator([80.0])
        draft = run_draft(gen)
        self.assertEqual(draft.sentences[0].text, "first text")
        self.assertEqual(gen.feedbacks, [""])


if __name__ == "__main__":
    unittest.main()
