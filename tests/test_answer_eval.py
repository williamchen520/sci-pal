"""Answer evaluation tests."""

from __future__ import annotations

import unittest

from eval.answer_eval import evaluate


class AnswerEvalTests(unittest.TestCase):
    def test_refusal_with_citations(self) -> None:
        gold = [{"id": "q1", "answer_points": [], "forbidden": []}]
        answers = [
            {
                "id": "q1",
                "answer": "The provided evidence does not contain the answer [P1].",
                "evidence_ids": ["[P1]"],
            }
        ]
        result = evaluate(gold, answers)
        self.assertEqual(result["summary"]["refusal_accuracy"], 1.0)

    def test_coverage(self) -> None:
        gold = [{"id": "q1", "answer_points": ["response rate 42%"], "forbidden": []}]
        answers = [{"id": "q1", "answer": "The response rate was 42% [P1].", "evidence_ids": ["[P1]"]}]
        result = evaluate(gold, answers)
        self.assertEqual(result["summary"]["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
