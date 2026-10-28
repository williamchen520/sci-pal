"""Adaptive QA budget tests."""

from __future__ import annotations

import unittest

from services.qa.budget import choose_top_k, is_complex


class BudgetTests(unittest.TestCase):
    def test_simple(self) -> None:
        self.assertFalse(is_complex("What is ICI rechallenge?"))
        self.assertEqual(choose_top_k("What is ICI rechallenge?"), 10)

    def test_complex_markers(self) -> None:
        self.assertTrue(is_complex("Review the evidence across HCC studies"))
        self.assertEqual(choose_top_k("Review the evidence across HCC studies"), 20)

    def test_long_question(self) -> None:
        question = "How does " + "very long context " * 10 + "affect outcomes?"
        self.assertTrue(is_complex(question))

    def test_disable(self) -> None:
        import os

        os.environ["SCIPAL_QA_ADAPTIVE_TOPK"] = "0"
        try:
            self.assertEqual(choose_top_k("Review the evidence"), 10)
        finally:
            os.environ.pop("SCIPAL_QA_ADAPTIVE_TOPK", None)


if __name__ == "__main__":
    unittest.main()
