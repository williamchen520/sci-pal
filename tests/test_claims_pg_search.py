from __future__ import annotations

import unittest
from unittest import mock

from services.claims import pg_search


class _FakePG:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql
        return self

    def fetchall(self):
        return [
            {
                "sentence_id": "s1",
                "paper_id": "p1",
                "quote": "tace improves survival",
                "paper_title": "T",
                "rank": 0.5,
            }
        ]

    def close(self):
        return None


class ClaimsPGSearchTests(unittest.TestCase):
    def test_search_uses_pg_fts(self):
        pg = _FakePG()
        claim = {
            "claim_id": "c1",
            "claim_text": "TACE improves survival",
            "qualifiers": {},
            "corpus": [],
        }
        with mock.patch.object(pg_search.pg_read, "get_claim", return_value=claim):
            with mock.patch.object(pg_search, "pg_connection", return_value=pg):
                with mock.patch.object(
                    pg_search.retrieval,
                    "build_queries",
                    return_value={"support": '"tace"', "refute": '"tace"'},
                ):
                    with mock.patch.object(
                        pg_search.retrieval,
                        "rank_candidates",
                        side_effect=lambda *a, **k: a[2],
                    ):
                        rows = pg_search.search_candidates("c1", limit=1)
        self.assertEqual(rows[0]["sentence_id"], "s1")
        self.assertIn("websearch_to_tsquery", pg.sql)


if __name__ == "__main__":
    unittest.main()
