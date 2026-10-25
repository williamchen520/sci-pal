"""Tests for section query construction."""

from __future__ import annotations

import unittest

from services.review.query_builder import build_section_query


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


if __name__ == "__main__":
    unittest.main()
