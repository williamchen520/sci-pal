"""Retraction flag tests (mocked HTTP, temp DB)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.trust_schema import migrate
from services.trust.retraction import check_doi, flag_paper, flags_for_papers


class RetractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        migrate(self.db)

    def test_openalex_retracted(self) -> None:
        def fake(url: str):
            if "openalex" in url:
                return {"id": "W1", "is_retracted": True}
            return {"message": {}}

        flags = check_doi("10.1/x", fake)
        self.assertEqual(flags[0]["flag_type"], "retracted")
        self.assertEqual(flags[0]["source"], "openalex")

    def test_crossref_correction(self) -> None:
        def fake(url: str):
            if "crossref" in url:
                return {"message": {"update-to": [{"type": "correction", "DOI": "10.1/y"}]}}
            return {}

        flags = check_doi("10.1/x", fake)
        self.assertEqual(flags[0]["flag_type"], "correction")

    def test_flag_and_query(self) -> None:
        conn = sqlite3.connect(self.db)
        flag_paper(conn, "p1", [{"flag_type": "retracted", "source": "openalex", "detail": "W1"}])
        result = flags_for_papers(conn, ["p1", "p2"])
        conn.close()
        self.assertEqual(result["p1"][0]["flag_type"], "retracted")
        self.assertNotIn("p2", result)

    def test_bad_doi_does_not_raise(self) -> None:
        def fake(url: str):
            raise RuntimeError("network down")

        self.assertEqual(check_doi("10.1/x", fake), [])


if __name__ == "__main__":
    unittest.main()
