"""Paper section tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import sections


class SectionTests(unittest.TestCase):
    def test_unknown_type(self) -> None:
        with self.assertRaises(ValueError):
            sections.paper_section("p1", "nope")

    def test_not_found(self) -> None:
        with mock.patch.object(sections, "paper_outline", return_value=[]):
            result = sections.paper_section("p1", "results")
        self.assertEqual(result["status"], "not_found")

    def test_section_summary(self) -> None:
        with mock.patch.object(
            sections,
            "paper_outline",
            return_value=[
                {
                    "section_path": "Results A",
                    "section_type": "results",
                    "first_para_id": "p1",
                    "paragraph_count": 1,
                }
            ],
        ):
            result = sections.paper_section("p1", "results")
        self.assertNotIn("paragraphs", result["sections"][0])
        self.assertEqual(result["sections"][0]["paragraph_count"], 1)

    def test_section_full(self) -> None:
        with mock.patch.object(
            sections,
            "paper_outline",
            return_value=[{"section_path": "Results A", "section_type": "results", "first_para_id": "p1", "paragraph_count": 1}],
        ), mock.patch.object(
            sections,
            "paper_paragraphs",
            return_value=[{"para_id": "p1", "section_level1": "body", "section_level2": "Results A"}],
        ):
            result = sections.paper_section("p1", "results", include_paragraphs=True)
        self.assertEqual(result["sections"][0]["paragraphs"][0]["para_id"], "p1")


if __name__ == "__main__":
    unittest.main()
