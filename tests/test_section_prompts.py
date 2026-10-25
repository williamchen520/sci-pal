"""Tests for section prompt construction (pure functions)."""

from __future__ import annotations

import unittest

from services.review.section_prompts import (
    build_write_prompt,
    count_citation_markers,
    detect_section_type,
    evidence_lines,
)

EVIDENCE = [
    {
        "evidence_id": "ev_p1_para1_0",
        "evidence_type": "fact",
        "content": "Treatment reduced mortality.",
        "original_quote": "mortality fell from 20% to 12%",
    }
]


class DetectSectionTypeTests(unittest.TestCase):
    def test_english_keywords(self) -> None:
        self.assertEqual(detect_section_type("Introduction"), "introduction")
        self.assertEqual(detect_section_type("Materials and Methods"), "methods")
        self.assertEqual(detect_section_type("Results"), "results")
        self.assertEqual(detect_section_type("Discussion"), "discussion")
        self.assertEqual(detect_section_type("Conclusion and Future Work"), "conclusion")
        self.assertEqual(detect_section_type("Mechanisms of resistance"), "body")

    def test_chinese_keywords(self) -> None:
        self.assertEqual(detect_section_type("引言"), "introduction")
        self.assertEqual(detect_section_type("讨论"), "discussion")
        self.assertEqual(detect_section_type("结论与展望"), "conclusion")


class EvidenceLinesTests(unittest.TestCase):
    def test_formats_id_type_content_and_quote(self) -> None:
        text = evidence_lines(EVIDENCE)
        self.assertIn("[ev_p1_para1_0] (fact) Treatment reduced mortality.", text)
        self.assertIn("Quote: mortality fell", text)

    def test_handles_enum_type(self) -> None:
        class Kind:
            value = "finding"

        text = evidence_lines([{"evidence_id": "e", "evidence_type": Kind(), "content": "c"}])
        self.assertIn("(finding)", text)


class BuildPromptTests(unittest.TestCase):
    SECTION = {"title": "Introduction", "description": "Set the stage"}

    def test_english_prompt_contains_structure(self) -> None:
        section_type, prompt = build_write_prompt(
            self.SECTION, EVIDENCE, review_type="narrative", language="en",
            section_index=0, total_sections=3,
        )
        self.assertEqual(section_type, "introduction")
        self.assertIn("Section position: Section 1 of 3", prompt)
        self.assertIn("INTRODUCTION", prompt)
        self.assertIn("Section title: Introduction", prompt)
        self.assertIn("Set the stage", prompt)
        self.assertIn("ev_p1_para1_0", prompt)
        self.assertIn("200-400 words", prompt)
        self.assertIn("[evidence_id] citation marker", prompt)

    def test_chinese_prompt_uses_chinese_sections(self) -> None:
        section_type, prompt = build_write_prompt(
            {"title": "引言", "description": "背景"}, EVIDENCE,
            language="zh", section_index=1, total_sections=5,
        )
        self.assertEqual(section_type, "introduction")
        self.assertIn("第 2 / 5 章", prompt)
        self.assertIn("写作流程（证据-声明矩阵）", prompt)
        self.assertIn("[证据ID] 引用标记", prompt)

    def test_previous_summary_only_when_provided(self) -> None:
        _, with_summary = build_write_prompt(self.SECTION, EVIDENCE, previous_summary="earlier text")
        _, without = build_write_prompt(self.SECTION, EVIDENCE)
        self.assertIn("earlier text", with_summary)
        self.assertNotIn("Previous sections summary", without)

    def test_feedback_block_only_in_revision(self) -> None:
        _, revised = build_write_prompt(self.SECTION, EVIDENCE, feedback="add citations")
        _, first = build_write_prompt(self.SECTION, EVIDENCE)
        self.assertIn("add citations", revised)
        self.assertIn("REVISING", revised)
        self.assertNotIn("REVISING", first)

    def test_review_type_label(self) -> None:
        _, prompt = build_write_prompt(self.SECTION, EVIDENCE, review_type="systematic")
        self.assertIn("Systematic Review", prompt)

    def test_unknown_review_type_falls_back(self) -> None:
        _, prompt = build_write_prompt(self.SECTION, EVIDENCE, review_type="weird")
        self.assertIn("Narrative Review", prompt)


class CitationMarkerTests(unittest.TestCase):
    def test_counts_markers(self) -> None:
        self.assertEqual(count_citation_markers("A [ev_1]. B [ev_2]."), 2)
        self.assertEqual(count_citation_markers("no markers"), 0)


if __name__ == "__main__":
    unittest.main()
