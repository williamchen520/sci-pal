"""Section type routing tests."""

from __future__ import annotations

import unittest

from services.search.section_types import classify_section, query_intent, section_prior


class SectionTypeTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_section("References"), "references")
        self.assertEqual(classify_section("Materials and Methods"), "methods")
        self.assertEqual(classify_section("Results"), "results")
        self.assertEqual(classify_section("Discussion"), "discussion")
        self.assertEqual(classify_section("Introduction"), "introduction")

    def test_intent(self) -> None:
        self.assertEqual(query_intent("What was the response rate?"), "results")
        self.assertEqual(query_intent("What inclusion criteria were used?"), "methods")
        self.assertEqual(query_intent("What are the limitations?"), "discussion")

    def test_prior(self) -> None:
        self.assertEqual(section_prior("results", "references"), -1.0)
        self.assertEqual(section_prior("results", "results"), 0.15)
        self.assertEqual(section_prior("results", "introduction"), 0.0)


if __name__ == "__main__":
    unittest.main()
