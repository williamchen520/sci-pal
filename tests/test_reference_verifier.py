"""Tests for bibliographic reference verification."""

from __future__ import annotations

import unittest

from services.quality.reference_verifier import (
    canonical_identifier,
    normalize_text,
    verify_metadata,
)


class VerifyMetadataTests(unittest.TestCase):
    def test_all_fields_match(self) -> None:
        result = verify_metadata(
            {"title": "Deep Learning", "year": 2015, "doi": "https://doi.org/10.1038/NATURE14539"},
            {
                "title": "Deep learning.",
                "year": "2015",
                "doi": "10.1038/nature14539",
                "journal": "Nature",
            },
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["method"], "identifier_lookup")
        self.assertEqual(result["fields"]["title"]["status"], "match")

    def test_title_mismatch_reports_both_values(self) -> None:
        result = verify_metadata(
            {"title": "Large language models for clinical diagnosis"},
            {"title": "Deep learning"},
        )
        self.assertEqual(result["status"], "mismatch")
        field = result["fields"]["title"]
        self.assertEqual(field["status"], "mismatch")
        self.assertIn("expected", field)
        self.assertIn("actual", field)

    def test_doi_variants_are_equal(self) -> None:
        for left, right in [
            ("10.1038/nature14539", "https://doi.org/10.1038/NATURE14539"),
            ("doi: 10.1038/nature14539", "10.1038/NATURE14539."),
        ]:
            result = verify_metadata({"doi": left}, {"doi": right})
            self.assertEqual(result["status"], "verified", (left, right))

    def test_year_formats_are_equal(self) -> None:
        self.assertEqual(
            verify_metadata({"year": "2015"}, {"year": "2015-05-28"})["status"], "verified"
        )
        self.assertEqual(
            verify_metadata({"year": 2015}, {"year": 2016})["status"], "mismatch"
        )

    def test_author_prefix_matches(self) -> None:
        actual = {"authors": ["LeCun, Yann", "Bengio, Yoshua", "Hinton, Geoffrey"]}
        result = verify_metadata({"authors": ["LeCun, Yann", "Bengio, Yoshua"]}, actual)
        self.assertEqual(result["status"], "verified")

    def test_author_prefix_mismatch(self) -> None:
        actual = {"authors": ["LeCun, Yann", "Bengio, Yoshua"]}
        result = verify_metadata({"authors": ["Hinton, Geoffrey"]}, actual)
        self.assertEqual(result["status"], "mismatch")

    def test_missing_field_needs_manual_review(self) -> None:
        result = verify_metadata({"journal": "Nature"}, {"title": "x"})
        self.assertEqual(result["status"], "manual_needed")
        self.assertEqual(result["fields"]["journal"]["status"], "missing")

    def test_unknown_field_is_uncheckable(self) -> None:
        result = verify_metadata({"abstract": "..."}, {"title": "x"})
        self.assertEqual(result["status"], "manual_needed")
        self.assertEqual(result["fields"]["abstract"]["status"], "uncheckable")

    def test_empty_expected_is_manual(self) -> None:
        self.assertEqual(verify_metadata({}, {"title": "x"})["status"], "manual_needed")

    def test_not_found_when_record_missing(self) -> None:
        self.assertEqual(
            verify_metadata({"doi": "10.1/x"}, None)["status"], "not_found"
        )

    def test_mismatch_wins_over_missing(self) -> None:
        result = verify_metadata(
            {"title": "A", "journal": "Nature"},
            {"title": "B"},
        )
        self.assertEqual(result["status"], "mismatch")

    def test_blank_expected_values_are_skipped(self) -> None:
        result = verify_metadata({"title": "Deep learning", "journal": ""}, {"title": "Deep learning"})
        self.assertEqual(result["status"], "verified")

    def test_first_author_alias_compares_against_authors(self) -> None:
        result = verify_metadata(
            {"first_author": "LeCun, Yann"},
            {"authors": ["LeCun, Yann", "Bengio, Yoshua"]},
        )
        self.assertEqual(result["status"], "verified")


class NormalizationTests(unittest.TestCase):
    def test_identifiers(self) -> None:
        self.assertEqual(canonical_identifier("doi", "DOI:10.1038/NATURE14539"), "10.1038/nature14539")
        self.assertEqual(canonical_identifier("pmid", "PMID: 28344011"), "28344011")
        self.assertEqual(canonical_identifier("pmcid", "pmc123456"), "PMC123456")
        self.assertEqual(
            canonical_identifier("arxiv_id", "https://arxiv.org/pdf/1706.03762v5.pdf"),
            "1706.03762",
        )

    def test_text_normalization(self) -> None:
        self.assertEqual(normalize_text("Deep-Learning: A Review."), "deeplearning a review")


if __name__ == "__main__":
    unittest.main()
