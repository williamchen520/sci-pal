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


class FakeReranker:
    def rerank(self, query, results, top_k=10):
        return [
            {**row, "rerank_score": 0.9 if row["para_id"] == "p2" else 0.1}
            for row in sorted(results, key=lambda r: r["para_id"], reverse=True)[:top_k]
        ]


class PGParagraphRetrieverTests(unittest.TestCase):
    def test_rerank_maps_to_hybrid_shape(self):
        retriever = PGParagraphRetriever("postgresql://example", reranker=FakeReranker())
        retriever.fts = FakeFTS()
        rows = retriever.search("q", top_k=2)
        self.assertEqual([row["para_id"] for row in rows], ["p2", "p1"])
        self.assertEqual(rows[0]["section_l1"], "Results")
        self.assertEqual(rows[0]["score"], 0.9)

    def test_empty_candidates_returns_empty(self):
        class Empty:
            def search(self, query, **kwargs):
                return []

        retriever = PGParagraphRetriever("postgresql://example", reranker=FakeReranker())
        retriever.fts = Empty()
        self.assertEqual(retriever.search("q"), [])


if __name__ == "__main__":
    unittest.main()
