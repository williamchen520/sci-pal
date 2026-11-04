from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.papers import pg_writes


class PaperPGWritesTests(unittest.TestCase):
    def test_enabled_flag(self):
        with mock.patch.dict(
            os.environ,
            {"SCIPAL_PAPER_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_writes.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_PAPER_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_writes.enabled())

    def test_disabled_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            with mock.patch.object(pg_writes, "enabled", return_value=False):
                self.assertFalse(pg_writes.update_workspace("p1", "ws1", db_path=db))
                self.assertFalse(
                    pg_writes.update_metadata_if_exists(
                        "p1", journal="J", year=2026, doi="10/x", db_path=db
                    )
                )


if __name__ == "__main__":
    unittest.main()

class _FakePG:
    def __init__(self):
        self.sql = ""
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return self


class PaperRowCoverageTests(unittest.TestCase):
    def test_full_metadata_columns(self):
        pg = _FakePG()
        pg_writes._upsert_paper_row(
            pg,
            {
                "paper_id": "p1",
                "title": "T",
                "keywords": "k1,k2",
                "volume": "12",
                "parse_status": "completed",
                "total_paragraphs": 3,
            },
        )
        self.assertIn("keywords", pg.sql)
        self.assertIn("parse_status", pg.sql)
        self.assertEqual(pg.params["keywords"], "k1,k2")
        self.assertEqual(pg.params["total_paragraphs"], 3)
        self.assertEqual(pg.params["parse_engine"], "xml")
