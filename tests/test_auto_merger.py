"""Auto merger tests (PostgreSQL read path mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from services.search.auto_merger import AutoMerger


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakePG:
    def __init__(self):
        self.closed = False

    def execute(self, sql, params):
        assert "FROM paragraphs" in sql
        return FakeCursor(
            [
                {"para_id": "p1", "text": "A", "page": 1, "sequence": 1},
                {"para_id": "p2", "text": "B", "page": 1, "sequence": 2},
                {"para_id": "p3", "text": "C", "page": 1, "sequence": 3},
            ]
        )

    def close(self):
        self.closed = True


class AutoMergerTests(unittest.TestCase):
    def test_merge(self) -> None:
        pg = FakePG()
        contexts = [
            {
                "section_id": "sec",
                "matched_para_ids": ["p1", "p2"],
                "matched_sentences": [{"sentence_id": "s1"}],
                "paragraphs": [{"para_id": "p1", "text": "A"}],
                "text": "A",
            }
        ]
        with mock.patch(
            "services.search.auto_merger.main_read_connection", return_value=pg
        ):
            merged = AutoMerger("unused").merge(contexts, min_hits=2, token_budget=100)
        self.assertTrue(pg.closed)
        self.assertTrue(merged[0]["auto_merged"])
        self.assertEqual(len(merged[0]["matched_sentences"]), 1)
        self.assertGreaterEqual(len(merged[0]["paragraphs"]), 2)


if __name__ == "__main__":
    unittest.main()
