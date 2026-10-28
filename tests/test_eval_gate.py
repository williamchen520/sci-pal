"""Eval gate comparison."""

from __future__ import annotations

import unittest

from eval.gate import compare


class GateTests(unittest.TestCase):
    def test_pass(self) -> None:
        result = compare({"recall@10": 0.5, "mrr": 0.4}, {"recall@10": 0.49, "mrr": 0.4}, 0.02)
        self.assertTrue(result["ok"])

    def test_fail(self) -> None:
        result = compare({"recall@10": 0.5}, {"recall@10": 0.40}, 0.02)
        self.assertFalse(result["ok"])
        self.assertEqual(result["failures"][0]["metric"], "recall@10")


if __name__ == "__main__":
    unittest.main()
