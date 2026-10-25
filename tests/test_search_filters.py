"""Tests for the three-stage filter pipeline."""

from __future__ import annotations

import unittest

from services.search.filters import (
    apply_post_filters,
    normalize_filters,
    translate_filters,
)


class NormalizeTests(unittest.TestCase):
    def test_none_and_empty(self) -> None:
        self.assertEqual(normalize_filters(None), {})
        self.assertEqual(normalize_filters({}), {})

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_filters({"year_from": 2020})

    def test_date_formats(self) -> None:
        self.assertEqual(normalize_filters({"date_from": "2020"})["date_from"], "2020-01-01")
        self.assertEqual(normalize_filters({"date_from": "2020-06"})["date_from"], "2020-06-01")
        self.assertEqual(
            normalize_filters({"date_to": "2020-06-15"})["date_to"], "2020-06-15"
        )

    def test_invalid_date(self) -> None:
        for value in ("20-01-01", "2020-13-01", "2020-02-30", "abc"):
            with self.assertRaises(ValueError, msg=value):
                normalize_filters({"date_from": value})

    def test_date_range_order(self) -> None:
        with self.assertRaises(ValueError):
            normalize_filters({"date_from": "2024-01-01", "date_to": "2023-01-01"})

    def test_language_alias(self) -> None:
        self.assertEqual(normalize_filters({"language": "ENG"})["language"], "en")
        self.assertEqual(normalize_filters({"language": "zh"})["language"], "zh")
        with self.assertRaises(ValueError):
            normalize_filters({"language": "english"})

    def test_document_type_and_identifiers(self) -> None:
        result = normalize_filters(
            {
                "document_type": "Journal Article",
                "identifiers": [
                    "https://doi.org/10.1038/NATURE14539",
                    "doi:10.1038/nature14539",
                    "PMID: 28344011",
                    "https://arxiv.org/abs/1706.03762v5",
                ],
            }
        )
        self.assertEqual(result["document_type"], ["Journal Article"])
        self.assertEqual(
            result["identifiers"],
            ["10.1038/nature14539", "28344011", "1706.03762"],
        )

    def test_author_empty_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_filters({"author": "   "})

    def test_non_mapping_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_filters(["date_from"])  # type: ignore[arg-type]


class TranslateTests(unittest.TestCase):
    def test_pubmed_builds_query_fragments(self) -> None:
        result = translate_filters(
            "pubmed",
            {
                "date_from": "2020-01-01",
                "date_to": "2024-12-31",
                "author": "LeCun",
                "language": "en",
                "document_type": "Journal Article",
                "identifiers": ["10.1/x"],
            },
        )
        self.assertIn("[Date - Publication]", result["query"])
        self.assertIn("LeCun[Author]", result["query"])
        self.assertIn("en[Language]", result["query"])
        self.assertIn("[Publication Type]", result["query"])
        self.assertEqual(result["post_filter"], ["identifiers"])
        self.assertIn("author", result["applied"])

    def test_openalex_uses_kwargs(self) -> None:
        result = translate_filters("openalex", {"date_from": "2020", "language": "en"})
        self.assertEqual(result["kwargs"], {"date_from": "2020-01-01", "language": "en"})
        self.assertEqual(result["query"], "")

    def test_local_defers_everything(self) -> None:
        filters = {"author": "LeCun", "language": "en"}
        result = translate_filters("local", filters)
        self.assertEqual(result["kwargs"], {})
        self.assertEqual(sorted(result["post_filter"]), ["author", "language"])

    def test_unknown_source_defers_everything(self) -> None:
        result = translate_filters("crossref", {"author": "LeCun"})
        self.assertEqual(result["post_filter"], ["author"])

    def test_empty_filters(self) -> None:
        result = translate_filters("pubmed", {})
        self.assertEqual(
            result, {"kwargs": {}, "query": "", "applied": [], "post_filter": []}
        )


class PostFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            {
                "record_id": "a",
                "year": 2023,
                "language": "eng",
                "authors": ["LeCun, Yann", "Bengio, Yoshua"],
                "document_type": "journal-article",
                "doi": "10.1038/nature14539",
            },
            {
                "record_id": "b",
                "publication_date": "2024-05-01",
                "language": "en",
                "authors": ["Hinton, Geoffrey"],
                "document_type": "review",
                "doi": "10.1/other",
            },
            {"record_id": "c"},
        ]

    def _ids(self, results) -> list[str]:
        return [item["record_id"] for item in results]

    def test_empty_filters_returns_copies(self) -> None:
        out = apply_post_filters(self.records, {})
        self.assertEqual(self._ids(out), ["a", "b", "c"])
        self.assertIsNot(out[0], self.records[0])

    def test_date_uses_year_fallback_and_drops_undated(self) -> None:
        out = apply_post_filters(self.records, {"date_from": "2024-01-01"})
        self.assertEqual(self._ids(out), ["b"])

    def test_date_range_includes_boundaries(self) -> None:
        out = apply_post_filters(self.records, {"date_from": "2023-01-01", "date_to": "2023-12-31"})
        self.assertEqual(self._ids(out), ["a"])

    def test_language_alias(self) -> None:
        self.assertEqual(self._ids(apply_post_filters(self.records, {"language": "en"})), ["a", "b"])

    def test_author_substring(self) -> None:
        self.assertEqual(self._ids(apply_post_filters(self.records, {"author": "lecun"})), ["a"])

    def test_document_type_normalizes_punctuation(self) -> None:
        self.assertEqual(
            self._ids(apply_post_filters(self.records, {"document_type": "Journal Article"})),
            ["a"],
        )

    def test_identifier_matches_doi_variants(self) -> None:
        self.assertEqual(
            self._ids(
                apply_post_filters(
                    self.records, {"identifiers": ["https://doi.org/10.1038/NATURE14539"]}
                )
            ),
            ["a"],
        )

    def test_filters_combine_with_and(self) -> None:
        out = apply_post_filters(self.records, {"language": "en", "author": "lecun"})
        self.assertEqual(self._ids(out), ["a"])

    def test_missing_fields_fail_strictly(self) -> None:
        out = apply_post_filters(self.records, {"language": "en", "date_to": "2030-01-01"})
        self.assertEqual(self._ids(out), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
