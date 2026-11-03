from __future__ import annotations

import unittest

from services.db.fallback_stats import record, reset, snapshot


class FallbackStatsTests(unittest.TestCase):
    def setUp(self):
        reset()

    def test_counts_by_component(self):
        record("papers_list")
        record("papers_list")
        record("papers_graph")
        self.assertEqual(snapshot(), {"papers_list": 2, "papers_graph": 1})

    def test_reset(self):
        record("papers_list")
        reset()
        self.assertEqual(snapshot(), {})


if __name__ == "__main__":
    unittest.main()
