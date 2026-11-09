from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.search.hybrid_search import HybridSearch


class ParadeDBRoutingTests(unittest.TestCase):
    def test_percent_100_uses_paradedb(self):
        searcher = HybridSearch.__new__(HybridSearch)
        with patch.object(
            searcher, "_paradedb_fts_search", return_value=[{"para_id": "p1"}]
        ) as parade:
            with patch.dict(
                os.environ,
                {
                    "SCIPAL_FTS_BACKEND": "sqlite",
                    "SCIPAL_FTS_PARADEDB_PERCENT": "100",
                },
            ):
                hits = searcher.fts_search("test query", top_k=1)
        self.assertEqual(hits, [{"para_id": "p1"}])
        parade.assert_called_once()

    def test_percent_0_does_not_use_paradedb(self):
        searcher = HybridSearch.__new__(HybridSearch)
        with patch.object(
            searcher, "_paradedb_fts_search", side_effect=AssertionError("should not run")
        ):
            with patch.dict(
                os.environ,
                {
                    "SCIPAL_FTS_BACKEND": "sqlite",
                    "SCIPAL_FTS_PARADEDB_PERCENT": "0",
                },
            ):
                self.assertEqual(searcher.fts_search("test query", top_k=1), [])


if __name__ == "__main__":
    unittest.main()
