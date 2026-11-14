"""Sentence evidence service tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import evidence


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.closed = False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _Cursor(self.rows)

    def close(self):
        self.closed = True


class PaperEvidenceTests(unittest.TestCase):
    def test_empty_query(self) -> None:
        with mock.patch.object(evidence, "corpus_connection") as conn:
            self.assertEqual(evidence.paper_evidence("p1", "   "), [])
        conn.assert_not_called()

    def test_scoped_query_and_limit(self) -> None:
        conn = _Conn([{"sentence_id": "s1", "score": 0.5}])
        with mock.patch.object(evidence, "_vector_candidates", return_value=[]), mock.patch.object(
            evidence, "corpus_connection", return_value=conn
        ):
            rows = evidence.paper_evidence("p1", "lycopene", top_k=100)
        self.assertEqual(rows[0]["sentence_id"], "s1")
        sql, params = conn.calls[0]
        self.assertIn("s.paper_id = %s", sql)
        self.assertIn("websearch_to_tsquery", sql)
        self.assertEqual(params, ("lycopene", "p1", 20))
        self.assertEqual(rows[0]["match_type"], "sentence_fts")
        self.assertTrue(conn.closed)

    def test_vector_candidates_limit_sentence_scope(self) -> None:
        conn = _Conn([{"sentence_id": "s1", "score": 0.5}])
        with mock.patch.object(
            evidence, "_vector_candidates", return_value=[{"para_id": "p1"}]
        ), mock.patch.object(evidence, "corpus_connection", return_value=conn):
            rows = evidence.paper_evidence("paper", "lipid macrophages", top_k=3)
        sql, params = conn.calls[0]
        self.assertIn("s.para_id = ANY(%s)", sql)
        self.assertIn(["p1"], params)
        self.assertEqual(rows[0]["match_type"], "paragraph_vector+sentence_fts")


if __name__ == "__main__":
    unittest.main()
