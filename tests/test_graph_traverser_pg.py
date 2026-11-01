"""P5 graph canary unit tests."""

from __future__ import annotations

import unittest

from services.search.graph_traverser_pg import PGGraphTraverser


class _FakePG:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def execute(self, sql, params=None):
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class GraphTraverserPGTests(unittest.TestCase):
    def test_neighbors_are_deduplicated_and_seeds_removed(self) -> None:
        rows = [
            {"paper_id": "p2", "relation": "cites", "via_paper_id": "p1",
             "confidence": 0.5, "title": "Two", "authors": "", "year": 2024, "journal": ""},
            {"paper_id": "p2", "relation": "cites", "via_paper_id": "p1",
             "confidence": 0.9, "title": "Two", "authors": "", "year": 2024, "journal": ""},
            {"paper_id": "p1", "relation": "cites", "via_paper_id": "p1",
             "confidence": 1.0, "title": "Seed", "authors": "", "year": 2024, "journal": ""},
        ]
        traverser = PGGraphTraverser(connector=lambda: _FakePG(rows))
        result = traverser.get_neighbors(["p1"], direction="out")
        self.assertEqual([item["paper_id"] for item in result], ["p2"])
        self.assertEqual(result[0]["confidence"], 0.9)

    def test_empty_seed_returns_empty(self) -> None:
        traverser = PGGraphTraverser(connector=lambda: _FakePG([]))
        self.assertEqual(traverser.get_neighbors([]), [])


if __name__ == "__main__":
    unittest.main()
