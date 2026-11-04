from __future__ import annotations

import unittest

from services.search.pg_vector import PGVectorParagraphSearch, vector_literal


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return self.rows


class PGVectorTests(unittest.TestCase):
    def test_vector_literal(self):
        self.assertEqual(vector_literal([0.1, -0.2]), "[0.100000,-0.200000]")

    def test_search_sql_and_filters(self):
        fake = FakeCursor(
            [
                {
                    "para_id": "p1",
                    "paper_id": "paper1",
                    "section_level1": "Intro",
                    "section_level2": None,
                    "text": "HCC",
                    "rank": 0.9,
                }
            ]
        )
        hits = PGVectorParagraphSearch(connector=lambda: fake).search(
            [0.1, 0.2], top_k=5, paper_id="paper1"
        )
        self.assertEqual(hits[0].para_id, "p1")
        self.assertIn("<=>", fake.sql)
        self.assertIn("e.paper_id = %s", fake.sql)

    def test_empty(self):
        self.assertEqual(
            PGVectorParagraphSearch(connector=lambda: object()).search([]), []
        )


if __name__ == "__main__":
    unittest.main()
