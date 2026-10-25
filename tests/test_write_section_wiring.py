"""Seam test: ``_write_section`` now delegates prompt building to section_prompts.

No model is loaded: the generator is built with ``object.__new__`` and only the
``llm`` attribute is provided.
"""

from __future__ import annotations

import unittest

from services.review.llm_client import LLMError
from services.review.models import EvidenceCard, ReviewSection
from services.review.review_generator import ReviewGenerator


class FakeLLM:
    def __init__(self, reply: str = "Draft text [ev_1].", error: Exception | None = None):
        self.reply = reply
        self.error = error
        self.seen: tuple[str, str] | None = None

    def chat(self, system: str, user: str) -> str:
        self.seen = (system, user)
        if self.error:
            raise self.error
        return self.reply


def make_generator(llm) -> ReviewGenerator:
    generator = object.__new__(ReviewGenerator)
    generator.llm = llm
    return generator


def section(title: str = "Introduction") -> ReviewSection:
    return ReviewSection(section_id="s1", title=title, description="desc")


def card() -> EvidenceCard:
    return EvidenceCard(
        evidence_id="ev_1",
        paper_id="p1",
        para_id="a1",
        content="treatment reduced mortality",
        original_quote="mortality fell",
    )


class WriteSectionWiringTests(unittest.TestCase):
    def test_returns_llm_text_and_builds_prompt(self) -> None:
        llm = FakeLLM()
        generator = make_generator(llm)
        out = generator._write_section(section(), [card()])
        self.assertEqual(out, "Draft text [ev_1].")
        system, user = llm.seen
        self.assertIn("Section title: Introduction", user)
        self.assertIn("[ev_1] (fact) treatment reduced mortality", user)
        self.assertIn("mortality fell", user)
        self.assertIn("academic review writer", system.lower())

    def test_chinese_language_selects_chinese_system_prompt(self) -> None:
        llm = FakeLLM()
        generator = make_generator(llm)
        generator._write_section(section("引言"), [card()], language="zh")
        system, user = llm.seen
        self.assertIn("章节标题：引言", user)
        self.assertIn("综述", system)

    def test_feedback_is_injected_on_revision(self) -> None:
        llm = FakeLLM()
        generator = make_generator(llm)
        generator._write_section(section(), [card()], feedback="add more evidence")
        _, user = llm.seen
        self.assertIn("add more evidence", user)
        self.assertIn("REVISING", user)

    def test_llm_error_falls_back_to_evidence_bullets(self) -> None:
        llm = FakeLLM(error=LLMError("down"))
        generator = make_generator(llm)
        out = generator._write_section(section(), [card()])
        self.assertIn("- treatment reduced mortality [ev_1]", out)


if __name__ == "__main__":
    unittest.main()
