"""Section summary builder + keyword search."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.build_summaries import build, summarize_section
from services.search.summary_search import SummarySearch


class SummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT,
                parent_id TEXT, level INTEGER, title TEXT, seq INTEGER);
            CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT,
                section_id TEXT, text TEXT, sequence INTEGER, page INTEGER);
            """
        )
        conn.execute("INSERT INTO sections VALUES ('s1','p1',NULL,1,'Efficacy',1)")
        conn.execute(
            "INSERT INTO paragraphs VALUES ('a','p1','s1','The response rate was 42%.',1,1)"
        )
        conn.execute(
            "INSERT INTO paragraphs VALUES ('b','p1','s1','Toxicity was manageable.',2,1)"
        )
        conn.commit()
        conn.close()

    def test_summarize_section(self) -> None:
        text = summarize_section("Efficacy", ["The response rate was 42%.", "Toxicity was manageable."])
        self.assertIn("Efficacy", text)
        self.assertIn("42%", text)

    def test_build_and_search(self) -> None:
        stats = build(self.db)
        self.assertEqual(stats["sections"], 1)
        results = SummarySearch(self.db).search("response rate")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["paper_id"], "p1")

    def test_no_terms(self) -> None:
        build(self.db)
        self.assertEqual(SummarySearch(self.db).search("the of and"), [])


if __name__ == "__main__":
    unittest.main()
