"""Tests for the durable reviews repository."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.review.review_repository import ReviewRepository


class ReviewRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = ReviewRepository(Path(self.tmp.name) / "research.db")

    def test_schema_is_created_lazily(self) -> None:
        self.repo.ensure_schema()
        conn = sqlite3.connect(self.repo.db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertIn("reviews", tables)

    def test_save_and_get_roundtrip(self) -> None:
        self.repo.save(
            review_id="rev_1",
            run_id="run_1",
            topic="demo",
            markdown="# body",
            stats={"verified": 3},
            references=[{"paper_id": "p1"}],
            warnings=["w"],
        )
        record = self.repo.get("rev_1")
        self.assertEqual(record["topic"], "demo")
        self.assertEqual(record["markdown"], "# body")
        self.assertEqual(record["stats"], {"verified": 3})
        self.assertEqual(record["references"], [{"paper_id": "p1"}])
        self.assertEqual(record["warnings"], ["w"])
        self.assertEqual(record["run_id"], "run_1")

    def test_save_is_idempotent_per_id(self) -> None:
        self.repo.save(review_id="rev_1", topic="a", markdown="first")
        self.repo.save(review_id="rev_1", topic="b", markdown="second")
        record = self.repo.get("rev_1")
        self.assertEqual(record["topic"], "b")
        self.assertEqual(len(self.repo.list()), 1)

    def test_list_returns_newest_first(self) -> None:
        self.repo.save(review_id="rev_old", topic="a", markdown="x", created_at="2026-01-01T00:00:00Z")
        self.repo.save(review_id="rev_new", topic="b", markdown="y", created_at="2026-02-01T00:00:00Z")
        self.assertEqual([row["review_id"] for row in self.repo.list()], ["rev_new", "rev_old"])

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.repo.get("nope"))

    def test_list_limit(self) -> None:
        for index in range(5):
            self.repo.save(review_id=f"rev_{index}", topic="t", markdown="m")
        self.assertEqual(len(self.repo.list(limit=2)), 2)

    def test_guard_is_persisted_and_returned(self) -> None:
        guard = {"unknown": 1, "unknown_ratio": 0.02, "counts": {"unknown": 1}}
        self.repo.save(review_id="rev_g", topic="t", markdown="m", guard=guard)
        self.assertEqual(self.repo.get("rev_g")["guard"], guard)

    def test_existing_rows_without_guard_return_none(self) -> None:
        self.repo.save(review_id="rev_plain", topic="t", markdown="m")
        self.assertIsNone(self.repo.get("rev_plain")["guard"])


if __name__ == "__main__":
    unittest.main()
