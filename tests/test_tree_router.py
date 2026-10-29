"""Tree router tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.tree_router import TreeRouter


class TreeRouterTests(unittest.TestCase):
    def test_beam_expands_relevant_child(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.executescript(
                """
                CREATE TABLE sections (
                    section_id TEXT, paper_id TEXT, parent_id TEXT,
                    title TEXT, depth INTEGER, path TEXT
                );
                """
            )
            conn.execute("INSERT INTO sections VALUES ('r1','paper',NULL,'Results',1,'Results')")
            conn.execute("INSERT INTO sections VALUES ('c1','paper','r1','Results',2,'Results › Results')")
            conn.execute("INSERT INTO sections VALUES ('c2','paper','r1','Methods',2,'Results › Methods')")
            conn.commit()
            conn.close()

            def fake_summary(query, top_k, paper_id):
                return [
                    {"section_id": "c1", "distance": 0.1},
                    {"section_id": "c2", "distance": 0.8},
                ]

            results = TreeRouter(db, summary_search=fake_summary).search(
                "response rate", ["paper"], beam=2, depth=2
            )
        ids = {item["section_id"] for item in results}
        self.assertIn("c1", ids)
        self.assertIn("r1", ids)


if __name__ == "__main__":
    unittest.main()
