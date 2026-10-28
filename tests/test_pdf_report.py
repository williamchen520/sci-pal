"""PDF report tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import pdf_report, risk_of_bias, systematic


class PdfReportTests(unittest.TestCase):
    def test_pdf_bytes(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
        conn.commit()
        migrate(db)
        project = systematic.create_project(conn, "HCC 报告", "HCC", {"intervention": "ICI"})
        conn.execute("INSERT INTO papers VALUES ('p1','Randomized trial','120 patients, OS improved.')")
        systematic.add_papers(conn, project, ["p1"])
        systematic.screen(conn, project, "p1", "include")
        systematic.add_evidence(
            conn, project, "p1", systematic.extract_evidence({"title": "T", "abstract": "120 patients, OS improved."})
        )
        risk_of_bias.save(conn, project, "p1", risk_of_bias.assess("Randomized trial with OS."))
        pdf = pdf_report.render_pdf(conn, project)
        conn.close()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)


if __name__ == "__main__":
    unittest.main()
