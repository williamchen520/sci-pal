"""Chroma filter shape regression test (paper_ids set must become list)."""

from __future__ import annotations

import unittest

from services.search.hybrid_search import chroma_paper_filter


class ChromaFilterTests(unittest.TestCase):
    def test_set_is_converted_to_list(self) -> None:
        result = chroma_paper_filter({"p1", "p2"})
        self.assertEqual(set(result["$in"]), {"p1", "p2"})
        self.assertIsInstance(result["$in"], list)

    def test_list_is_preserved(self) -> None:
        result = chroma_paper_filter(["p1", "p2"])
        self.assertEqual(result["$in"], ["p1", "p2"])


if __name__ == "__main__":
    unittest.main()
