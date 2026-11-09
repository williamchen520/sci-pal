"""Tests for the paper-title recall channel (PostgreSQL mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from services.review.title_recall import best_paragraphs, recall, recall_papers_by_title


class Cursor:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakePG:
    def execute(self, sql, params=None):
        if "FROM abstracts" in sql:
            return Cursor(rows=[{"pmid": "a1"}])
        if "FROM paragraphs" in sql:
            return Cursor(rows=[
                {"para_id": "p1a", "paper_id": "p1", "section_level1": "Intro",
                 "section_level2": "", "text": "sepsis without the receptor", "title": "TLR4 signaling in sepsis"},
                {"para_id": "p1b", "paper_id": "p1", "section_level1": "Intro",
                 "section_level2": "", "text": "TLR4 drives sepsis in macrophages", "title": "TLR4 signaling in sepsis"},
            ])
        return Cursor(rows=[{"paper_id": "p1"}])

    def close(self):
        pass


class TitleRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patch = mock.patch("services.review.title_recall._pg_connection", return_value=FakePG())
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_recall_finds_title_matches(self) -> None:
        self.assertEqual(recall_papers_by_title("unused.db", ["TLR4", "sepsis"]), ["p1"])

    def test_best_paragraphs_prefers_more_term_hits(self) -> None:
        rows = best_paragraphs("unused.db", "p1", ["TLR4", "sepsis"], per_paper=1)
        self.assertEqual(rows[0]["para_id"], "p1b")

    def test_recall_attaches_paragraphs(self) -> None:
        results = recall("unused.db", ["TLR4", "sepsis"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["paper_id"], "p1")
        self.assertTrue(results[0]["paragraphs"])

    def test_limits_are_env_tunable(self) -> None:
        import os
        from unittest.mock import patch

        from services.review.review_generator import _title_recall_limits

        with patch.dict(os.environ, {"SCIPAL_TITLE_RECALL_LIMIT": "10", "SCIPAL_TITLE_RECALL_MAX": "5"}):
            self.assertEqual(_title_recall_limits(), (10, 5))
        os.environ.pop("SCIPAL_TITLE_RECALL_LIMIT", None)
        os.environ.pop("SCIPAL_TITLE_RECALL_MAX", None)
        self.assertEqual(_title_recall_limits(), (10, 8))


if __name__ == "__main__":
    unittest.main()
