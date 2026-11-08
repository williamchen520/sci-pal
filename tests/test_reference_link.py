"""Review references -> local papers by DOI (PostgreSQL mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from services.review.reference_link import enrich_references, normalize_doi


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakePG:
    def __init__(self):
        self.closed = False

    def execute(self, sql, params):
        assert "lower(doi)" in sql
        return FakeCursor({"paper_id": "paper_A"} if params[0] == "10.1016/j.x.2026.001" else None)

    def close(self):
        self.closed = True


class ReferenceLinkTests(unittest.TestCase):
    def test_normalize_doi_strips_prefixes(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1/ABC"), "10.1/abc")
        self.assertEqual(normalize_doi("doi:10.2/X"), "10.2/x")

    def test_matching_reference_gets_paper_id_and_url(self) -> None:
        refs = [{"doi": "https://doi.org/10.1016/j.x.2026.001", "title": "A"}]
        with mock.patch(
            "services.review.reference_link.main_read_connection", return_value=FakePG()
        ):
            enrich_references(refs, "unused")
        self.assertEqual(refs[0]["paper_id"], "paper_A")
        self.assertTrue(refs[0]["doi_url"].startswith("https://doi.org/"))

    def test_unmatched_reference_keeps_url_only(self) -> None:
        refs = [{"doi": "10.9999/nope", "title": "B"}]
        with mock.patch(
            "services.review.reference_link.main_read_connection", return_value=FakePG()
        ):
            enrich_references(refs, "unused")
        self.assertNotIn("paper_id", refs[0])
        self.assertIn("doi_url", refs[0])

    def test_reference_without_doi_is_untouched(self) -> None:
        refs = [{"title": "C"}]
        with mock.patch(
            "services.review.reference_link.main_read_connection", return_value=FakePG()
        ):
            enrich_references(refs, "unused")
        self.assertEqual(refs[0], {"title": "C"})


if __name__ == "__main__":
    unittest.main()
