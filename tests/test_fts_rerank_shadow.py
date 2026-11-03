from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.fts_rerank_shadow import _case_id, _gold_para, _load_cases, _ndcg, _query


class FtsRerankShadowTests(unittest.TestCase):
    def test_gold_para_from_sentence(self):
        case = {"gold_sentence_ids": ["para_paper_1_0008_sent_001"]}
        self.assertEqual(_gold_para(case), "para_paper_1_0008")

    def test_seed_jsonl_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seed.jsonl"
            path.write_text('{"id":"q1","question":"What is X?","evidence":["para_p_sent_1"]}\n', encoding="utf-8")
            cases = _load_cases(path)
        self.assertEqual(_case_id(cases[0]), "q1")
        self.assertEqual(_query(cases[0]), "What is X?")
        self.assertEqual(_gold_para(cases[0]), "para_p")

    def test_ndcg_binary(self):
        self.assertEqual(_ndcg(["p2"], "p2"), 1.0)
        self.assertAlmostEqual(_ndcg(["x", "p2"], "p2"), 1.0 / 1.584962500721156)
        self.assertEqual(_ndcg(["x"], "p2"), 0.0)


if __name__ == "__main__":
    unittest.main()
