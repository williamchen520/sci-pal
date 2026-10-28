"""DOI/title record import tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import systematic


class ImportRecordsTests(unittest.TestCase):
    def test_match_by_doi_and_title(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT, doi TEXT)"
        )
        conn.commit()
        migrate(db)
        conn.execute("INSERT INTO papers VALUES ('p1','Trial A','', '10.1/a')")
        conn.execute("INSERT INTO papers VALUES ('p2','Trial B','', '')")
        project = systematic.create_project(conn, "P")
        result = systematic.import_records(
            conn,
            project,
            [
                {"doi": "10.1/A"},
                {"title": "trial b"},
                {"doi": "10.9/missing", "title": "Unknown"},
            ],
        )
        counts = systematic.prisma(conn, project)
        conn.close()
        self.assertEqual(result["matched"], 2)
        self.assertEqual(result["unmatched"], 1)
        self.assertEqual(counts["identified"], 2)


if __name__ == "__main__":
    unittest.main()
