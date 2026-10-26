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

    def test_limits_are_env_tunable(self) -> None:
        import os
        from unittest.mock import patch

        from services.review.review_generator import _title_recall_limits

        with patch.dict(
            os.environ, {"SCIPAL_TITLE_RECALL_LIMIT": "10", "SCIPAL_TITLE_RECALL_MAX": "5"}
        ):
            self.assertEqual(_title_recall_limits(), (10, 5))


class AbstractRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "abstracts.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (
                id INTEGER PRIMARY KEY, pmid TEXT, doi TEXT, title TEXT, abstract TEXT,
                authors TEXT, journal TEXT, year TEXT, topic TEXT, source TEXT
            );
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                pmid UNINDEXED, title, abstract, authors, journal, topic,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            """
        )
        conn.execute(
            "INSERT INTO papers (pmid, title, abstract, authors, journal, year) "
            "VALUES ('9001', 'Sepsis biomarkers', 'TLR4 and sepsis outcomes', 'A', 'J', '2026')"
        )
        conn.execute(
            "INSERT INTO papers_fts (pmid, title, abstract, authors, journal, topic) "
            "VALUES ('9001', 'Sepsis biomarkers', 'TLR4 and sepsis outcomes', 'A', 'J', '')"
        )
        conn.commit()
        conn.close()

    def test_recalls_abstract_titles(self) -> None:
        from services.review.title_recall import recall_abstracts_by_title

        self.assertEqual(recall_abstracts_by_title(self.db, ["TLR4", "sepsis"]), ["9001"])

    def test_abstract_for_requires_term_hit(self) -> None:
        from services.review.title_recall import abstract_for

        record = abstract_for(self.db, "9001", ["TLR4", "sepsis"])
        self.assertIsNotNone(record)
        self.assertEqual(record["title"], "Sepsis biomarkers")
        self.assertIsNone(abstract_for(self.db, "9001", ["melanoma"]))


if __name__ == "__main__":
    unittest.main()
