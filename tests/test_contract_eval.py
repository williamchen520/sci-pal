"""Contract evaluator helper tests."""

from __future__ import annotations

import unittest

from eval.contract_eval import paragraph_sentences, strict_sentences


class ContractEvalTests(unittest.TestCase):
    def test_units(self) -> None:
        payload = {
            "evidence": [
                {
                    "highlight": [{"sentence_id": "s1"}],
                    "paragraph_details": [{"sentence_ids": ["s1", "s2"]}],
                }
            ]
        }
        self.assertEqual(strict_sentences(payload, 10), ["s1"])
        self.assertEqual(paragraph_sentences(payload), {"s1", "s2"})


if __name__ == "__main__":
    unittest.main()
