"""Review references -> local papers by DOI."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.review.reference_link import enrich_references, normalize_doi


class ReferenceLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "papers.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, doi TEXT)")
        conn.execute("INSERT INTO papers VALUES ('paper_A', '10.1016/J.X.2026.001')")
        conn.commit()
        conn.close()

    def test_normalize_doi_strips_prefixes(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1/ABC"), "10.1/abc")
        self.assertEqual(normalize_doi("doi:10.2/X"), "10.2/x")

    def test_matching_reference_gets_paper_id_and_url(self) -> None:
        references = [{"doi": "https://doi.org/10.1016/j.x.2026.001", "title": "A"}]
        enrich_references(references, self.db)
        self.assertEqual(references[0]["paper_id"], "paper_A")
        self.assertTrue(references[0]["doi_url"].startswith("https://doi.org/"))

    def test_unmatched_reference_keeps_url_only(self) -> None:
        references = [{"doi": "10.9999/nope", "title": "B"}]
        enrich_references(references, self.db)
        self.assertNotIn("paper_id", references[0])
        self.assertIn("doi_url", references[0])

    def test_reference_without_doi_is_untouched(self) -> None:
        references = [{"title": "C"}]
        enrich_references(references, self.db)
        self.assertEqual(references[0], {"title": "C"})


if __name__ == "__main__":
    unittest.main()
