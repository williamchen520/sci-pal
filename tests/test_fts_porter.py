"""FTS porter rebuild / 20-query metric tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.fts_porter_compare import metrics, terms_for
from scripts.rebuild_fts_porter import copy_database, rebuild


class PorterRebuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "source.db"
        conn = sqlite3.connect(self.source)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT);
            CREATE TABLE paragraphs (
              para_id TEXT PRIMARY KEY, paper_id TEXT, section_level1 TEXT,
              section_level2 TEXT, text TEXT
            );
            INSERT INTO papers VALUES ('p1','A long enough title','a','j');
            INSERT INTO paragraphs VALUES ('x1','p1','Intro','','This is a searchable paragraph.');
            """
        )
        conn.commit()
        conn.close()

    def test_rebuilds_porter_copy(self) -> None:
        target = Path(self.tmp.name) / "target.db"
        copy_database(self.source, target)
        report = rebuild(target)
        self.assertEqual(report["integrity"], "ok")
        self.assertEqual(report["paragraphs_fts_rows"], 1)
        conn = sqlite3.connect(target)
        try:
            sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='paragraphs_fts'"
            ).fetchone()[0]
            self.assertIn("porter", sql)
        finally:
            conn.close()


class PorterMetricTests(unittest.TestCase):
    def test_terms_are_deduplicated_and_bounded(self) -> None:
        terms = terms_for("How does STAT1 regulate interferon response in cancer?")
        self.assertIn("stat1", terms)
        self.assertLessEqual(len(terms), 8)

    def test_metrics(self) -> None:
        result = metrics(["p1", "p2"], {"p2"})
        self.assertEqual(result["recall@10"], 1.0)
        self.assertEqual(result["mrr"], 0.5)
        self.assertGreater(result["ndcg@10"], 0)


if __name__ == "__main__":
    unittest.main()
