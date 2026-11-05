from __future__ import annotations

import unittest

from services.watch.pg_store import dedup_key


class WatchPGStoreTests(unittest.TestCase):
    def test_dedup_doi(self):
        self.assertEqual(
            dedup_key("https://doi.org/10.1/X", "T"), "doi:10.1/x"
        )

    def test_dedup_title(self):
        self.assertEqual(dedup_key(None, "A B!"), dedup_key(None, "ab"))


if __name__ == "__main__":
    unittest.main()
