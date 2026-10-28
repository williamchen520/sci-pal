"""Sentence seed search tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.sentence_seeds import SentenceSeedSearch


class SentenceSeedTests(unittest.TestCase):
    def test_search(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE sentences (sentence_id TEXT, para_id TEXT, text TEXT);
                CREATE VIRTUAL TABLE sentences_fts USING fts5(
                    sentence_id, paper_id, section_id, text
                );
                """
            )
            conn.execute("INSERT INTO sentences VALUES ('s1','p1','response rate was 42%')")
            conn.execute("INSERT INTO sentences VALUES ('s2','p2','toxicity was mild')")
            conn.execute("INSERT INTO sentences_fts VALUES ('s1','paper','sec','response rate was 42%')")
            conn.execute("INSERT INTO sentences_fts VALUES ('s2','paper','sec','toxicity was mild')")
            conn.commit()
            conn.close()
            results = SentenceSeedSearch(db).search("response rate", top_k=10)
        self.assertEqual(results[0]["para_id"], "p1")
        self.assertEqual(results[0]["rank"], 1)

    def test_empty(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            sqlite3.connect(db).close()
            self.assertEqual(SentenceSeedSearch(db).search("the and"), [])
