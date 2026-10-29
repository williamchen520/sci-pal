"""Grounding checks tests."""

from __future__ import annotations

import unittest

from services.qa.grounding import check_grounding


class GroundingTests(unittest.TestCase):
    def test_supported(self) -> None:
        result = check_grounding(
            "The response rate was 42% [P1].",
            "In this cohort the response rate was 42% among treated patients.",
        )
        self.assertTrue(result["grounded"])

    def test_parametric(self) -> None:
        result = check_grounding(
            "The capital of France is Paris [P1].",
            "Hepatocellular carcinoma response to immunotherapy was evaluated.",
        )
        self.assertFalse(result["grounded"])

    def test_uncited(self) -> None:
        result = check_grounding(
            "The boiling point of mercury is 356.7 degrees.",
            "Mercury exposure was measured in this study.",
        )
        self.assertFalse(result["grounded"])


if __name__ == "__main__":
    unittest.main()
