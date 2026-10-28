"""Citation intent classifier and backfill."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.citation_intent_schema import migrate
from services.search.citation_intent import classify


class CitationIntentTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify("However, this contradicts the trial."), "contrast")
        self.assertEqual(classify("This is consistent with prior work."), "support")
        self.assertEqual(classify("The study enrolled 120 patients."), "mention")

    def test_backfill(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, text TEXT);
            CREATE TABLE sentence_links (link_id TEXT PRIMARY KEY, sentence_id TEXT,
                target_type TEXT, intent TEXT);
            """
        )
        conn.execute("INSERT INTO sentences VALUES ('s1','However, this contradicts prior work.')")
        conn.execute("INSERT INTO sentences VALUES ('s2','The trial enrolled 120 patients.')")
        conn.execute("INSERT INTO sentence_links VALUES ('l1','s1','citation',NULL)")
        conn.execute("INSERT INTO sentence_links VALUES ('l2','s2','citation',NULL)")
        conn.commit()
        conn.close()

        stats = migrate(db)
        self.assertEqual(stats["updated"], 2)
        conn = sqlite3.connect(db)
        intents = dict(conn.execute("SELECT link_id, intent FROM sentence_links").fetchall())
        conn.close()
        self.assertEqual(intents["l1"], "contrast")
        self.assertEqual(intents["l2"], "mention")


if __name__ == "__main__":
    unittest.main()
