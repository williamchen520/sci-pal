"""Sufficiency heuristic tests (abstention signal)."""

from __future__ import annotations

import unittest

from services.qa.sufficiency import evaluate

GOOD_EVIDENCE = [
    {
        "text": "The response rate was 42% in the rechallenge cohort.",
        "score": 0.9,
    }
]
OFF_TOPIC = [{"text": "Mercury is toxic to aquatic organisms.", "score": 0.99}]


class SufficiencyTests(unittest.TestCase):
    def test_supported(self) -> None:
        result = evaluate("What was the response rate in the rechallenge cohort?", GOOD_EVIDENCE)
        self.assertTrue(result["sufficient"])

    def test_low_coverage(self) -> None:
        result = evaluate("What is the boiling point of mercury?", OFF_TOPIC)
        self.assertFalse(result["sufficient"])

    def test_low_score(self) -> None:
        result = evaluate(
            "What was the response rate?",
            [{"text": "The response rate was 42%.", "score": 0.01}],
        )
        self.assertFalse(result["sufficient"])

    def test_empty(self) -> None:
        self.assertFalse(evaluate("Anything?", [])["sufficient"])


if __name__ == "__main__":
    unittest.main()
