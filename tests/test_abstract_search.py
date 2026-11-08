from __future__ import annotations

import unittest

from services.search.abstract_search import AbstractSearch


class AbstractSearchTests(unittest.TestCase):
    def test_retired_channels_are_noop(self) -> None:
        search = AbstractSearch()
        self.assertEqual(search.search("ICI rechallenge"), [])
        self.assertEqual(search.vector_search("ICI rechallenge"), [])
        self.assertEqual(search.fts_search("ICI rechallenge"), [])


if __name__ == "__main__":
    unittest.main()
