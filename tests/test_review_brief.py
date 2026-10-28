"""Systematic review brief tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import brief, risk_of_bias, systematic


class BriefTests(unittest.TestCase):
    def test_brief_sections(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
        conn.commit()
        migrate(db)
        conn.execute(
            "INSERT INTO papers VALUES ('p1','Randomized HCC trial','Randomized 120 patients, OS improved.')"
        )
        project = systematic.create_project(
            conn, "HCC review", "HCC", {"intervention": "ICI"}, owner="default"
        )
        systematic.add_papers(conn, project, ["p1"])
        systematic.screen(conn, project, "p1", "include")
        row = systematic.extract_evidence(
            {"title": "Randomized HCC trial", "abstract": "Randomized 120 patients, OS improved."}
        )
        systematic.add_evidence(conn, project, "p1", row)
        risk_of_bias.save(conn, project, "p1", risk_of_bias.assess("Randomized trial with OS."))
        text = brief.build_brief(conn, project)
        conn.close()
        self.assertIn("# HCC review", text)
        self.assertIn("## PICO", text)
        self.assertIn("## PRISMA", text)
        self.assertIn("## 证据表", text)
        self.assertIn("## 风险偏倚", text)
        self.assertIn("p1", text)


if __name__ == "__main__":
    unittest.main()
