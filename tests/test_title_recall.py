"""Tests for the paper-title recall channel."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.review.title_recall import best_paragraphs, recall, recall_papers_by_title


class TitleRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT);
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                paper_id UNINDEXED, title, authors, journal,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            CREATE TABLE paragraphs (
                para_id TEXT PRIMARY KEY, paper_id TEXT, section_level1 TEXT,
                section_level2 TEXT, text TEXT, sequence INTEGER
            );
            """
        )
        conn.executemany(
            "INSERT INTO papers VALUES (?, ?, '', '')",
            [
                ("p1", "TLR4 signaling in sepsis"),
                ("p2", "Metabolic dysregulation review"),
            ],
        )
        conn.executemany(
            "INSERT INTO papers_fts (paper_id, title, authors, journal) VALUES (?, ?, '', '')",
            [("p1", "TLR4 signaling in sepsis"), ("p2", "Metabolic dysregulation review")],
        )
        conn.executemany(
            "INSERT INTO paragraphs (para_id, paper_id, section_level1, text, sequence) "
            "VALUES (?, ?, 'Intro', ?, 0)",
            [
                ("p1a", "p1", "sepsis without the receptor"),
                ("p1b", "p1", "TLR4 drives sepsis in macrophages"),
                ("p2a", "p2", "metabolic inflammation only"),
            ],
        )
        conn.commit()
        conn.close()

    def test_recall_finds_title_matches(self) -> None:
        ids = recall_papers_by_title(self.db, ["TLR4", "sepsis"])
        self.assertEqual(ids, ["p1"])

    def test_best_paragraphs_prefers_more_term_hits(self) -> None:
        rows = best_paragraphs(self.db, "p1", ["TLR4", "sepsis"], per_paper=1)
        self.assertEqual(rows[0]["para_id"], "p1b")

    def test_recall_attaches_paragraphs(self) -> None:
        results = recall(self.db, ["TLR4", "sepsis"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["paper_id"], "p1")
        self.assertTrue(results[0]["paragraphs"])

    def test_unknown_db_returns_empty(self) -> None:
        self.assertEqual(recall_papers_by_title(Path(self.tmp.name) / "missing.db", ["x"]), [])


if __name__ == "__main__":
    unittest.main()
