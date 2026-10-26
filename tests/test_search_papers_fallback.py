"""search_papers fallback when the index has no ``papers`` collection."""

from __future__ import annotations

import sqlite3
import unittest

from services.search.hybrid_search import HybridSearch


def make_search():
    search = object.__new__(HybridSearch)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT, year TEXT)"
    )
    conn.execute("INSERT INTO papers VALUES ('p1', 'Paper one', 'A', 'J', '2026')")
    conn.execute("INSERT INTO papers VALUES ('p2', 'Paper two', 'B', 'J', '2025')")
    search.conn = conn
    search.paper_collection = None
    search.vector_search = lambda query, top_k=10: [{"paper_id": "p1", "score": 0.8}]
    search.fts_search = lambda query, top_k=10: [
        {"paper_id": "p1", "score": 0.6},
        {"paper_id": "p2", "score": 0.5},
    ]
    return search


class PaperFallbackTests(unittest.TestCase):
    def test_fallback_ranks_by_best_paragraph_score(self) -> None:
        results = make_search().search_papers("anything", top_k=2)
        self.assertEqual([item["paper_id"] for item in results], ["p1", "p2"])
        self.assertAlmostEqual(results[0]["score"], 0.8)

    def test_fallback_respects_top_k(self) -> None:
        self.assertEqual(len(make_search().search_papers("anything", top_k=1)), 1)

    def test_fallback_returns_empty_on_search_error(self) -> None:
        search = make_search()
        search.vector_search = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        self.assertEqual(search.search_papers("anything", top_k=2), [])


if __name__ == "__main__":
    unittest.main()
