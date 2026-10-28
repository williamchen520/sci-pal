"""PICO extraction and double-screening kappa."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import kappa, pico, systematic


class PicoTests(unittest.TestCase):
    def test_extract(self) -> None:
        text = (
            "Immune checkpoint inhibitor rechallenge in patients with hepatocellular carcinoma "
            "versus initial ICI; overall survival and ORR were assessed."
        )
        result = pico.extract(text)
        self.assertIn("hepatocellular carcinoma", result["population"].lower())
        self.assertTrue(result["intervention"])
        self.assertTrue(result["comparator"])
        self.assertTrue(result["outcome"])

    def test_auto_pico(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, abstract TEXT)")
        conn.commit()
        migrate(db)
        project = systematic.create_project(conn, "HCC", "hepatocellular carcinoma")
        conn.execute("INSERT INTO papers VALUES ('p1','HCC trial','HCC patients received ICI versus placebo.')")
        systematic.add_papers(conn, project, ["p1"])
        result = pico.auto_pico(conn, project)
        population = result["population"].lower()
        self.assertTrue("hcc" in population or "hepatocellular" in population)
        conn.close()


class KappaTests(unittest.TestCase):
    def test_kappa(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        migrate(db)
        conn = sqlite3.connect(db)
        project = systematic.create_project(conn, "P")
        systematic.add_papers(conn, project, ["p1", "p2", "p3"])
        for reviewer, decisions in [
            ("alice", ["include", "include", "exclude"]),
            ("bob", ["include", "exclude", "exclude"]),
        ]:
            for paper, decision in zip(["p1", "p2", "p3"], decisions):
                systematic.screen(conn, project, paper, decision, reviewer=reviewer)
        result = kappa.kappa(conn, project)
        conn.close()
        self.assertEqual(result["pairs"], 3)
        self.assertAlmostEqual(result["agreement"], 0.6667, places=3)
        self.assertIsNotNone(result["kappa"])


if __name__ == "__main__":
    unittest.main()
