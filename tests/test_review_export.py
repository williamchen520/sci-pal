"""Export/import roundtrip tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import export, risk_of_bias, systematic


class ExportTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
        conn.commit()
        migrate(db)
        project = systematic.create_project(conn, "HCC", "HCC", {"intervention": "ICI"}, owner="alice")
        systematic.add_papers(conn, project, ["p1"])
        systematic.screen(conn, project, "p1", "include", reviewer="alice")
        systematic.adjudicate(conn, project, "p1", "include", editor="alice")
        systematic.add_evidence(
            conn, project, "p1",
            {"design": "RCT", "sample_size": "120", "effect": "42%"},
        )
        risk_of_bias.save(conn, project, "p1", risk_of_bias.assess("Randomized trial with OS."))
        systematic.add_member(conn, project, "bob")
        systematic.log_event(conn, project, "alice", "screened", "p1", "include")

        data = export.export_project(conn, project)
        result = export.import_project(conn, data, owner="alice")
        new_id = result["project_id"]
        self.assertNotEqual(new_id, project)
        self.assertEqual(result["papers"], 1)
        self.assertEqual(systematic.prisma(conn, new_id)["included"], 1)
        self.assertEqual(len(systematic.list_evidence(conn, new_id)), 1)
        self.assertEqual(systematic.members(conn, new_id)[0]["member"], "bob")
        conn.close()


if __name__ == "__main__":
    unittest.main()
