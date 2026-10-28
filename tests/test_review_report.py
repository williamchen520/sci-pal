"""HTML review report and RoB chart tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import report, risk_of_bias, rob_svg, systematic


class ReportTests(unittest.TestCase):
    def test_html_report(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
        conn.commit()
        migrate(db)
        project = systematic.create_project(conn, "HCC <review>", "HCC", {"intervention": "ICI"})
        conn.execute("INSERT INTO papers VALUES ('p1','Randomized trial','120 patients, OS improved.')")
        systematic.add_papers(conn, project, ["p1"])
        systematic.screen(conn, project, "p1", "include")
        systematic.add_evidence(
            conn, project, "p1", systematic.extract_evidence({"title": "T", "abstract": "120 patients, OS improved."})
        )
        risk_of_bias.save(conn, project, "p1", risk_of_bias.assess("Randomized trial with OS."))
        html = report.render_html(conn, project)
        conn.close()
        self.assertIn("HCC &lt;review&gt;", html)
        self.assertIn("Evidence table", html)
        self.assertIn("Risk of bias", html)
        self.assertIn("<svg", html)

    def test_rob_svg(self) -> None:
        rows = [
            {"domain": "randomization", "judgement": "low"},
            {"domain": "randomization", "judgement": "high"},
            {"domain": "reporting", "judgement": "some concerns"},
        ]
        svg = rob_svg.render(rows)
        self.assertIn("<svg", svg)
        self.assertIn("randomization", svg)


if __name__ == "__main__":
    unittest.main()
