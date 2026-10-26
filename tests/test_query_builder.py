"""Tests for section query construction."""

from __future__ import annotations

import unittest

from services.review.query_builder import (
    build_section_query,
    count_term_hits,
    is_paper_relevant,
)


class BuildSectionQueryTests(unittest.TestCase):
    def test_generic_terms_are_dropped_when_specific_exist(self) -> None:
        query = build_section_query(["TLR4", "signaling", "sepsis", "inflammation"])
        self.assertEqual(query, "TLR4 sepsis")

    def test_caps_terms(self) -> None:
        query = build_section_query(["TLR4", "sepsis", "NLRP3", "caspase"])
        self.assertEqual(query, "TLR4 sepsis NLRP3")

    def test_all_generic_falls_back_to_original(self) -> None:
        query = build_section_query(["inflammation", "immune"])
        self.assertEqual(query, "inflammation immune")

    def test_deduplicates_case_insensitively(self) -> None:
        query = build_section_query(["TLR4", "tlr4", "sepsis"])
        self.assertEqual(query, "TLR4 sepsis")

    def test_falls_back_to_title(self) -> None:
        query = build_section_query([], title="Toll-like receptor 4 in sepsis")
        self.assertEqual(query, "Toll-like receptor 4")

    def test_custom_max_terms(self) -> None:
        query = build_section_query(["TLR4", "sepsis", "NLRP3"], max_terms=1)
        self.assertEqual(query, "TLR4")


class RelevanceTests(unittest.TestCase):
    def test_counts_distinct_terms(self) -> None:
        text = "Sepsis-induced acute lung injury involves TLR4 signaling"
        self.assertEqual(count_term_hits(text, ["TLR4", "sepsis"]), 2)
        self.assertEqual(count_term_hits(text, ["TLR4", "sepsis", "caspase"]), 2)

    def test_two_term_query_needs_two_hits(self) -> None:
        self.assertFalse(is_paper_relevant("chronic inflammation review", ["TLR4", "sepsis"]))
        self.assertTrue(is_paper_relevant("TLR4 in sepsis", ["TLR4", "sepsis"]))

    def test_single_term_query_needs_one_hit(self) -> None:
        self.assertTrue(is_paper_relevant("a sepsis study", ["sepsis"]))
        self.assertFalse(is_paper_relevant("a metabolic study", ["sepsis"]))

    def test_no_terms_means_relevant(self) -> None:
        self.assertTrue(is_paper_relevant("anything", []))

    def test_title_must_mention_a_query_term(self) -> None:
        body = "this review mentions sepsis and TLR4 in passing"
        self.assertFalse(
            is_paper_relevant(body, ["TLR4", "sepsis"], title="Metabolic dysregulation review")
        )
        self.assertTrue(
            is_paper_relevant(body, ["TLR4", "sepsis"], title="TLR4 signaling in sepsis")
        )


if __name__ == "__main__":
    unittest.main()
