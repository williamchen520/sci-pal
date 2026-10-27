"""ContextExpander: section path + sentence highlight."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.context_expander import ContextExpander


class ContextExpanderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT,
                parent_id TEXT, level INTEGER, title TEXT, seq INTEGER, path TEXT, depth INTEGER);
            CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT, section_id TEXT,
                text TEXT, sequence INTEGER, page INTEGER,
                section_level1 TEXT, section_level2 TEXT, section_level3 TEXT);
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT,
                text TEXT, sequence INTEGER, page INTEGER, bbox TEXT, section_id TEXT,
                char_start INTEGER, char_end INTEGER);
            """
        )
        conn.execute("INSERT INTO sections VALUES ('s1','p1',NULL,1,'Results',1,'1',1)")
        conn.execute("INSERT INTO sections VALUES ('s2','p1','s1',2,'Efficacy',2,'1.1',2)")
        conn.execute(
            "INSERT INTO paragraphs VALUES ('para1','p1','s2','First sentence. Second sentence about response.',1,3,NULL,NULL,NULL)"
        )
        conn.execute(
            "INSERT INTO sentences VALUES ('sent1','para1','p1','First sentence.',1,3,'1,2,3,4','s2',0,15)"
        )
        conn.execute(
            "INSERT INTO sentences VALUES ('sent2','para1','p1','Second sentence about response.',2,3,'5,6,7,8','s2',16,47)"
        )
        conn.commit()
        conn.close()

    def test_section_path_and_highlight(self) -> None:
        expander = ContextExpander(self.db)
        units = expander.expand(
            [{"para_id": "para1", "score": 1.0}],
            query="response",
            max_parents=1,
        )
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["section_path"], ["Results", "Efficacy"])
        self.assertEqual(units[0]["matched_sentences"][0]["sentence_id"], "sent2")
        self.assertIn("►Second sentence about response.◄", units[0]["text"])

    def test_window_mode(self) -> None:
        expander = ContextExpander(self.db)
        units = expander.expand(
            [{"para_id": "para1", "score": 1.0}], mode="window", max_parents=1
        )
        self.assertEqual(units[0]["mode"], "window")
        self.assertEqual(units[0]["section_path"], ["Results", "Efficacy"])


if __name__ == "__main__":
    unittest.main()
