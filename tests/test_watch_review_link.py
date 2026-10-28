"""Watch run -> systematic review project."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import systematic


class WatchImportTests(unittest.TestCase):
    def test_add_from_watch(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE watch_items (run_id INTEGER, paper_id TEXT)")
        conn.commit()
        migrate(db)
        project = systematic.create_project(conn, "P")
        conn.execute("INSERT INTO watch_items VALUES (7, 'paper_a')")
        conn.execute("INSERT INTO watch_items VALUES (7, 'paper_b')")
        conn.commit()
        added = systematic.add_from_watch(conn, project, 7)
        counts = systematic.prisma(conn, project)
        conn.close()
        self.assertEqual(added, 2)
        self.assertEqual(counts["identified"], 2)


if __name__ == "__main__":
    unittest.main()
