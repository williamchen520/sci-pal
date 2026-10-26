"""HybridRetriever must reuse the process-wide HybridSearch (no third model)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import services.search.hybrid_retriever as hybrid_retriever


class HybridRetrieverSharedTests(unittest.TestCase):
    def test_uses_shared_searcher(self) -> None:
        sentinel = object()
        with patch.object(hybrid_retriever, "get_shared_hybrid", return_value=sentinel):
            retriever = hybrid_retriever.HybridRetriever(use_online=False, verbose=False)
        self.assertIs(retriever.local_searcher, sentinel)


if __name__ == "__main__":
    unittest.main()
