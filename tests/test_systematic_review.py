"""Systematic review: PRISMA counts, screening, evidence extraction."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import systematic


class SystematicReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)"
        )
        conn.commit()
        conn.close()
        migrate(self.db)
        self.conn = sqlite3.connect(self.db)
        self.project = systematic.create_project(
            self.conn,
            "HCC",
            "hepatocellular carcinoma",
            {"intervention": "ICI rechallenge", "comparator": "initial ICI"},
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_prisma(self) -> None:
        systematic.add_papers(self.conn, self.project, ["p1", "p2", "p3"])
        systematic.screen(self.conn, self.project, "p1", "include")
        systematic.screen(self.conn, self.project, "p2", "exclude", "wrong population")
        counts = systematic.prisma(self.conn, self.project)
        self.assertEqual(counts["identified"], 3)
        self.assertEqual(counts["included"], 1)
        self.assertEqual(counts["excluded"], 1)
        self.assertEqual(counts["pending"], 1)

    def test_extract_evidence(self) -> None:
        paper = {
            "title": "Randomized trial of ICI rechallenge in HCC",
            "abstract": "In this randomized study, 120 patients received ICI rechallenge. "
            "The objective response rate was 42% and overall survival improved (HR 0.65).",
        }
        row = systematic.extract_evidence(paper, {"intervention": "ICI rechallenge"})
        self.assertEqual(row["design"], "RCT")
        self.assertEqual(row["sample_size"], "120")
        self.assertEqual(row["intervention"], "ICI rechallenge")
        self.assertIn("42%", row["effect"])
        self.assertTrue(row["source_sentence"])

    def test_evidence_table(self) -> None:
        self.conn.execute(
            "INSERT INTO papers VALUES ('p1','Randomized trial','120 patients received treatment. Response rate 42%.')"
        )
        self.conn.commit()
        systematic.add_papers(self.conn, self.project, ["p1"])
        paper = self.conn.execute(
            "SELECT paper_id, title, abstract FROM papers WHERE paper_id='p1'"
        ).fetchone()
        row = systematic.extract_evidence(
            {"paper_id": paper[0], "title": paper[1], "abstract": paper[2]},
            {"intervention": "drug"},
        )
        systematic.add_evidence(self.conn, self.project, "p1", row)
        rows = systematic.list_evidence(self.conn, self.project)
        self.assertEqual(len(rows), 1)
        self.assertIn("design", rows[0])
        self.assertIn("paper_id", systematic.evidence_csv(self.conn, self.project))

    def test_prisma_uses_latest_decision(self) -> None:
        systematic.add_papers(self.conn, self.project, ["p1"])
        systematic.screen(self.conn, self.project, "p1", "include")
        systematic.screen(self.conn, self.project, "p1", "exclude", "second look")
        counts = systematic.prisma(self.conn, self.project)
        self.assertEqual(counts["included"], 0)
        self.assertEqual(counts["excluded"], 1)
        self.assertEqual(counts["screened"], 1)

    def test_conflicts(self) -> None:
        systematic.add_papers(self.conn, self.project, ["p1", "p2"])
        systematic.screen(self.conn, self.project, "p1", "include", reviewer="alice")
        systematic.screen(self.conn, self.project, "p1", "exclude", reviewer="bob")
        systematic.screen(self.conn, self.project, "p2", "include", reviewer="alice")
        systematic.screen(self.conn, self.project, "p2", "include", reviewer="bob")
        result = systematic.conflicts(self.conn, self.project)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["paper_id"], "p1")
        self.assertEqual(set(result[0]["decisions"]), {"alice", "bob"})


if __name__ == "__main__":
    unittest.main()
