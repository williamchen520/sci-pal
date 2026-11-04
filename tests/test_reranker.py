from __future__ import annotations

import unittest
from unittest.mock import patch

from services.search.reranker import Reranker


class FakeModel:
    def __init__(self):
        self.pairs = None

    def predict(self, pairs, batch_size=32):
        self.pairs = pairs
        return [float(index) for index, _ in enumerate(pairs)]


class RerankerTests(unittest.TestCase):
    def test_truncates_and_caps_items(self):
        reranker = Reranker.__new__(Reranker)
        reranker.model = FakeModel()
        results = [{"text": "x" * 1000, "id": i} for i in range(5)]
        with patch.dict(
            "os.environ",
            {"SCIPAL_RERANK_MAX_ITEMS": "3", "SCIPAL_RERANK_MAX_CHARS": "100"},
        ):
            out = reranker.rerank("q", results, top_k=3)
        self.assertEqual(len(reranker.model.pairs), 3)
        self.assertTrue(all(len(doc) == 100 for _, doc in reranker.model.pairs))
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
