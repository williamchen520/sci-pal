"""Summary vector search fallback tests (no collection)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.search.summary_vector_search import SummaryVectorSearch


class SummaryVectorTests(unittest.TestCase):
    def test_missing_collection_is_safe(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            search = SummaryVectorSearch(Path(tmp) / "chroma")
            self.assertFalse(search.available())
            self.assertEqual(search.search("anything"), [])


if __name__ == "__main__":
    unittest.main()
