"""Auto merger tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.auto_merger import AutoMerger


class AutoMergerTests(unittest.TestCase):
    def test_merge(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE paragraphs (para_id TEXT, section_id TEXT, text TEXT, "
                "sequence INTEGER, page INTEGER)"
            )
            conn.execute("INSERT INTO paragraphs VALUES ('p1','sec','A',1,1)")
            conn.execute("INSERT INTO paragraphs VALUES ('p2','sec','B',2,1)")
            conn.execute("INSERT INTO paragraphs VALUES ('p3','sec','C',3,1)")
            conn.commit()
            conn.close()
            contexts = [
                {
                    "section_id": "sec",
                    "matched_para_ids": ["p1", "p2"],
                    "matched_sentences": [{"sentence_id": "s1"}],
                    "paragraphs": [{"para_id": "p1", "text": "A"}],
                    "text": "A",
                }
            ]
            merged = AutoMerger(db).merge(contexts, min_hits=2, token_budget=100)
        self.assertTrue(merged[0]["auto_merged"])
        self.assertEqual(len(merged[0]["matched_sentences"]), 1)
        self.assertGreaterEqual(len(merged[0]["paragraphs"]), 2)


if __name__ == "__main__":
    unittest.main()
