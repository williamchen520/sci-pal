"""Search path weighting tests."""

from __future__ import annotations

import unittest

from code_rag.ranking import path_weight


class PathWeightTests(unittest.TestCase):
    def test_test_question_does_not_penalize_tests(self) -> None:
        self.assertGreater(path_weight("which test verifies view copy", "tests/test_a.py"), 1.0)

    def test_implementation_question_penalizes_tests(self) -> None:
        self.assertLess(path_weight("which function normalizes counts", "tests/test_a.py"), 1.0)

    def test_negated_test_is_not_a_test_question(self) -> None:
        self.assertLess(path_weight("which read symbol is not the test helper", "tests/test_a.py"), 1.0)

    def test_source_and_benchmark(self) -> None:
        self.assertEqual(path_weight("anything", "src/pkg/a.py"), 1.0)
        self.assertLess(path_weight("anything", "benchmarks/b.py"), 1.0)


if __name__ == "__main__":
    unittest.main()
