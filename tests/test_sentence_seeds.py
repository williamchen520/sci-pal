"""Sentence seed search tests (PostgreSQL mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from services.search.sentence_seeds import SentenceSeedSearch


class Cursor:
    def fetchall(self):
        return [{"para_id": "p1", "rank": 0.5}, {"para_id": "p1", "rank": 0.7}]


class FakePG:
    def execute(self, sql, params=None):
        return Cursor()

    def close(self):
        pass


class SentenceSeedTests(unittest.TestCase):
    def test_search(self) -> None:
        with mock.patch("services.db.pg_pool.pg_connection", return_value=FakePG()):
            results = SentenceSeedSearch().search("response rate", top_k=10)
        self.assertEqual(results[0]["para_id"], "p1")
        self.assertEqual(results[0]["rank"], 1)

    def test_empty(self) -> None:
        self.assertEqual(SentenceSeedSearch().search("the and"), [])


if __name__ == "__main__":
    unittest.main()
