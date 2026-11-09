from __future__ import annotations

import unittest

from services.search.pg_fts import ParagraphHit
from services.search.pg_paragraph_retriever import PGParagraphRetriever


class FakeFTS:
    def search(self, query, **kwargs):
        return [
            ParagraphHit("p1", "paper1", "Intro", None, "alpha", 1.0),
            ParagraphHit("p2", "paper2", "Results", None, "beta", 0.5),
        ]


class PGParagraphRetrieverTests(unittest.TestCase):
    def test_maps_fts_hits_to_hybrid_shape(self):
        retriever = PGParagraphRetriever("postgresql://example")
        retriever.fts = FakeFTS()
        rows = retriever.search("q", top_k=2)
        self.assertEqual([row["para_id"] for row in rows], ["p1", "p2"])
        self.assertEqual(rows[0]["section_l1"], "Intro")
        self.assertEqual(rows[0]["score"], 1.0)

    def test_empty_candidates_returns_empty(self):
        class Empty:
            def search(self, query, **kwargs):
                return []

        retriever = PGParagraphRetriever("postgresql://example")
        retriever.fts = Empty()
        self.assertEqual(retriever.search("q"), [])


if __name__ == "__main__":
    unittest.main()
