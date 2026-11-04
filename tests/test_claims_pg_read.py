from __future__ import annotations

import unittest
from unittest import mock

from services.claims import pg_read


class _FakePG:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        return None


class ClaimsPGReadTests(unittest.TestCase):
    def test_list(self):
        pg = _FakePG([{"claim_id": "c1"}])
        with mock.patch.object(pg_read, "pg_connection", return_value=pg):
            rows = pg_read.list_claims(5)
        self.assertEqual(rows[0]["claim_id"], "c1")
        self.assertIn("limit", pg.sql.lower())

    def test_card_parses_json(self):
        card = pg_read._card(
            {
                "claim_id": "c1",
                "qualifiers_json": '{"population": "HCC"}',
                "corpus_json": '["p1"]',
                "writing_brief": '{"key": "v"}',
            }
        )
        self.assertEqual(card["qualifiers"]["population"], "HCC")
        self.assertEqual(card["corpus"], ["p1"])
        self.assertEqual(card["writing_brief"]["key"], "v")


if __name__ == "__main__":
    unittest.main()
