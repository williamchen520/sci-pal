"""Claim–evidence builder tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.build_claims import build, claims_for_paper


class ClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, doi TEXT);
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, paper_id TEXT, text TEXT);
            CREATE TABLE citations (citation_id TEXT PRIMARY KEY, doi TEXT);
            CREATE TABLE sentence_links (link_id TEXT PRIMARY KEY, sentence_id TEXT,
                target_type TEXT, target_id TEXT, intent TEXT);
            """
        )
        conn.execute("INSERT INTO papers VALUES ('p1','10.1/a')")
        conn.execute("INSERT INTO papers VALUES ('p2','10.1/b')")
        conn.execute(
            "INSERT INTO sentences VALUES ('s1','p1','The response rate was 42% in the trial.')"
        )
        conn.execute(
            "INSERT INTO sentences VALUES ('s2','p2','The trial reported a response rate of 42% in patients.')"
        )
        conn.execute("INSERT INTO citations VALUES ('c1','10.1/b')")
        conn.execute(
            "INSERT INTO sentence_links VALUES ('l1','s1','citation','c1','support')"
        )
        conn.commit()
        conn.close()

    def test_build_and_query(self) -> None:
        stats = build(self.db)
        self.assertEqual(stats["claims"], 1)
        self.assertEqual(stats["evidence"], 1)
        conn = sqlite3.connect(self.db)
        claims = claims_for_paper(conn, "p1")
        conn.close()
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["evidence"][0]["sentence_id"], "s2")
        self.assertEqual(claims[0]["evidence"][0]["relation"], "support")

    def test_no_self_citation(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE citations SET doi = '10.1/a'")
        conn.commit()
        conn.close()
        stats = build(self.db)
        self.assertEqual(stats["claims"], 0)


if __name__ == "__main__":
    unittest.main()
