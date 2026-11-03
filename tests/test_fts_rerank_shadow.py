from __future__ import annotations

import unittest

from scripts.fts_rerank_shadow import _gold_para, _ndcg


class FtsRerankShadowTests(unittest.TestCase):
    def test_gold_para_from_sentence(self):
        case = {"gold_sentence_ids": ["para_paper_1_0008_sent_001"]}
        self.assertEqual(_gold_para(case), "para_paper_1_0008")

    def test_ndcg_binary(self):
        self.assertEqual(_ndcg(["p2"], "p2"), 1.0)
        self.assertAlmostEqual(_ndcg(["x", "p2"], "p2"), 1.0 / 1.584962500721156)
        self.assertEqual(_ndcg(["x"], "p2"), 0.0)


if __name__ == "__main__":
    unittest.main()
