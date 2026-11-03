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

    def test_cross_document_union_does_not_count(self) -> None:
        evidence = [
            {"text": "Boiling is a phase transition.", "score": 0.95},
            {"text": "Mercury is toxic to aquatic organisms.", "score": 0.004},
        ]
        result = evaluate("What is the boiling point of mercury?", evidence)
        self.assertFalse(result["sufficient"])
        self.assertEqual(result["top_item_coverage"], 0.3333)

    def test_short_question_needs_full_coverage(self) -> None:
        evidence = [
            {"text": "France is a country in Europe.", "score": 0.9},
            {"text": "Paris is the capital city.", "score": 0.8},
        ]
        result = evaluate("What is the capital of France?", evidence)
        self.assertFalse(result["sufficient"])
        self.assertEqual(result["min_coverage"], 1.0)

    def test_four_token_question_allows_half_coverage(self) -> None:
        evidence = [
            {
                "text": "ICI rechallenge is increasingly used in hepatocellular carcinoma.",
                "score": 0.9,
            }
        ]
        result = evaluate(
            "What is ICI rechallenge in hepatocellular carcinoma?", evidence
        )
        self.assertTrue(result["sufficient"])
        self.assertEqual(result["min_coverage"], 0.5)

    def test_long_question_allows_partial_coverage(self) -> None:
        evidence = [
            {
                "text": "Single-cell analysis reveals heterogeneity in the tumor microenvironment.",
                "score": 0.9,
            }
        ]
        result = evaluate(
            "How does single-cell analysis reveal tumor heterogeneity and treatment resistance?",
            evidence,
        )
        self.assertTrue(result["sufficient"])
        self.assertLess(result["min_coverage"], 0.5)

    def test_long_question_can_use_multiple_passages(self) -> None:
        evidence = [
            {"text": "The study describes salinization.", "score": 0.95},
            {"text": "It represents a relationship between soil and water.", "score": 0.8},
        ]
        result = evaluate(
            "How does the study describe the relationship between salinization and represents?",
            evidence,
        )
        self.assertTrue(result["sufficient"])
        self.assertGreater(result["union_coverage"], result["top_item_coverage"])

    def test_empty(self) -> None:
        self.assertFalse(evaluate("Anything?", [])["sufficient"])


if __name__ == "__main__":
    unittest.main()
