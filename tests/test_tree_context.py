"""Tree context builder tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.tree_context import TreeContextBuilder


class TreeContextTests(unittest.TestCase):
    def test_build(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE papers (paper_id TEXT, title TEXT);
                CREATE TABLE sections (section_id TEXT, paper_id TEXT, title TEXT,
                    path TEXT, depth INTEGER);
                CREATE TABLE paragraphs (para_id TEXT, paper_id TEXT, section_id TEXT,
                    text TEXT, sequence INTEGER, page INTEGER);
                CREATE TABLE sentences (sentence_id TEXT, para_id TEXT, text TEXT,
                    sequence INTEGER, page INTEGER);
                """
            )
            conn.execute("INSERT INTO papers VALUES ('paper','Title')")
            conn.execute(
                "INSERT INTO sections VALUES ('sec','paper','Results','Intro › Results',2)"
            )
            conn.execute(
                "INSERT INTO paragraphs VALUES ('p1','paper','sec','Response rate was 42%.',1,3)"
            )
            conn.execute(
                "INSERT INTO paragraphs VALUES ('p2','paper','sec','Toxicity was mild.',2,3)"
            )
            conn.execute(
                "INSERT INTO sentences VALUES ('s1','p1','Response rate was 42%.',1,3)"
            )
            conn.execute("INSERT INTO sentences VALUES ('s2','p2','Toxicity was mild.',1,3)")
            conn.commit()
            conn.close()

            contexts = TreeContextBuilder(db).build(
                [{"para_id": "p1", "rerank_score": 0.9}], "response rate", token_budget=200
            )
            self.assertEqual(len(contexts), 1)
            self.assertEqual(contexts[0]["section_id"], "sec")
            self.assertEqual(contexts[0]["matched_sentences"][0]["sentence_id"], "s1")
            self.assertIn("tokens", contexts[0])


if __name__ == "__main__":
    unittest.main()
