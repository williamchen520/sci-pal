"""E0 harness scoring tests."""

from __future__ import annotations

import unittest

from eval.code_rag_stack.harness import ndcg_at_k, rank, summarize


class HarnessScoringTests(unittest.TestCase):
    def test_rank_and_ndcg(self) -> None:
        self.assertEqual(rank(["a", "b"], "b"), 2)
        self.assertIsNone(rank(["a"], "b"))
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], "b", 10), 1 / 1.584962500721156)

    def test_summary_counts_hits(self) -> None:
        rows = [
            {"file_rank": 1, "symbol_rank": 1, "file_ndcg10": 1.0, "latency_ms": 10},
            {"file_rank": None, "symbol_rank": 5, "file_ndcg10": 0.0, "latency_ms": 20},
        ]
        result = summarize(rows)
        self.assertEqual(result["cases"], 2)
        self.assertEqual(result["file_hit@1"], 0.5)
        self.assertEqual(result["file_hit@5"], 0.5)
        self.assertEqual(result["symbol_hit@5"], 1.0)


if __name__ == "__main__":
    unittest.main()
