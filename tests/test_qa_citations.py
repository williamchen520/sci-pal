"""Paragraph citation helper tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.qa.citations import paragraph_citation


class CitationTests(unittest.TestCase):
    def test_paragraph_citation(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE sentences (sentence_id TEXT, para_id TEXT, sequence INTEGER)"
            )
            conn.execute("INSERT INTO sentences VALUES ('s1','p1',1)")
            conn.execute("INSERT INTO sentences VALUES ('s2','p1',2)")
            conn.commit()
            conn.close()
            result = paragraph_citation("p1", db)
        self.assertEqual(result["paragraph_id"], "p1")
        self.assertEqual(result["sentence_ids"], ["s1", "s2"])

    def test_empty(self) -> None:
        self.assertEqual(paragraph_citation(""), {})
