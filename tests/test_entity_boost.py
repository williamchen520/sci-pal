from __future__ import annotations

import unittest

from services.search.entity_boost import apply_entity_boost


class EntityBoostTests(unittest.TestCase):
    def test_boost_does_not_expand_candidates(self):
        fused = [{"para_id": "a", "rrf_score": 0.02}, {"para_id": "b", "rrf_score": 0.01}]
        hits = [{"para_id": "a"}, {"para_id": "c"}]
        affected = apply_entity_boost(fused, hits, mode="boost", weight=0.1)
        self.assertEqual(affected, 1)
        self.assertEqual([row["para_id"] for row in fused], ["a", "b"])
        self.assertGreater(fused[0]["rrf_score"], 0.02)
        self.assertNotIn("c", [row["para_id"] for row in fused])

    def test_append_is_legacy(self):
        fused = [{"para_id": "a", "rrf_score": 0.02}]
        hits = [{"para_id": "a"}, {"para_id": "c"}]
        affected = apply_entity_boost(fused, hits, mode="append")
        self.assertEqual(affected, 1)
        self.assertEqual([row["para_id"] for row in fused], ["a", "c"])

    def test_off(self):
        fused = [{"para_id": "a", "rrf_score": 0.02}]
        self.assertEqual(apply_entity_boost(fused, [{"para_id": "a"}], mode="off"), 0)


if __name__ == "__main__":
    unittest.main()
