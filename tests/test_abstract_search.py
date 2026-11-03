from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.abstract_search import AbstractSearch


class AbstractSearchTests(unittest.TestCase):
    def test_fts_query_with_question_mark_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "abstracts.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE papers (pmid TEXT, doi TEXT, title TEXT, abstract TEXT,
                  authors TEXT, journal TEXT, year TEXT, topic TEXT);
                CREATE VIRTUAL TABLE papers_fts USING fts5(
                  pmid UNINDEXED, title, abstract, authors, journal, topic UNINDEXED
                );
                INSERT INTO papers VALUES ('1','10.1/x','HCC trial','ICI rechallenge', 'A','J','2026','T');
                INSERT INTO papers_fts VALUES ('1','HCC trial','ICI rechallenge','A','J','T');
                """
            )
            conn.commit()
            conn.close()
            search = AbstractSearch.__new__(AbstractSearch)
            search.db_path = path
            hits = search.fts_search("What is ICI rechallenge?", top_k=5)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["pmid"], "1")


if __name__ == "__main__":
    unittest.main()
