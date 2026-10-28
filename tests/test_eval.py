"""Evaluation harness: retrieval and answer metrics."""

from __future__ import annotations

import unittest

from eval.answer_eval import evaluate as eval_answers
from eval.answer_eval import point_covered
from eval.retrieval_eval import evaluate as eval_retrieval


class RetrievalEvalTests(unittest.TestCase):
    def test_metrics(self) -> None:
        gold = [
            {"id": "q1", "question": "a", "evidence": ["s1", "s2"]},
            {"id": "q2", "question": "b", "evidence": ["s9"]},
            {"id": "q3", "question": "c", "evidence": []},
        ]
        responses = {
            "a": {"evidence": [{"highlight": [{"sentence_id": "s2"}, {"sentence_id": "s3"}]}]},
            "b": {"evidence": [{"highlight": [{"sentence_id": "s8"}]}]},
            "c": {"evidence": []},
        }
        result = eval_retrieval(gold, lambda q, k: responses[q], top_k=5)
        summary = result["summary"]
        self.assertEqual(summary["questions"], 2)
        self.assertAlmostEqual(summary["recall@5"], 0.25, places=4)  # q1 1/2 + q2 0
        self.assertAlmostEqual(summary["mrr"], 0.5, places=4)
        self.assertEqual(summary["refusal_accuracy"], 1.0)

    def test_perfect(self) -> None:
        gold = [{"id": "q", "question": "a", "evidence": ["s1"]}]
        payload = {"evidence": [{"highlight": [{"sentence_id": "s1"}]}]}
        summary = eval_retrieval(gold, lambda q, k: payload)["summary"]
        self.assertEqual(summary["recall@10"], 1.0)
        self.assertEqual(summary["mrr"], 1.0)

    def test_section_metrics(self) -> None:
        gold = [{"id": "q", "question": "a", "evidence": ["s1", "s2"]}]
        payload = {
            "evidence": [
                {
                    "highlight": [{"sentence_id": "s1"}],
                    "paragraph_details": [{"sentence_ids": ["s1", "s2"]}],
                }
            ],
            "summaries": [{"section_id": "sec1"}],
        }
        sections = {"s1": "sec1", "s2": "sec1"}
        result = eval_retrieval(
            gold, lambda q, k: payload, top_k=10, section_of=lambda sid: sections.get(sid)
        )["summary"]
        self.assertEqual(result["section_recall@10"], 1.0)
        self.assertEqual(result["summary_section_recall@10"], 1.0)
        self.assertEqual(result["paragraph_sentence_recall@10"], 1.0)


class AnswerEvalTests(unittest.TestCase):
    def test_point_covered(self) -> None:
        self.assertTrue(point_covered("22% vs 6%", "The ORR was 22% compared with 6%."))
        self.assertFalse(point_covered("22% vs 6%", "The ORR was high."))

    def test_metrics_and_refusal(self) -> None:
        gold = [
            {"id": "a", "answer_points": ["22% vs 6%"], "forbidden": ["all patients benefit"]},
            {"id": "b", "answer_points": []},
        ]
        answers = [
            {"id": "a", "answer": "ORR was 22% vs 6% [P1]."},
            {"id": "b", "answer": "No relevant information was found."},
        ]
        summary = eval_answers(gold, answers)["summary"]
        self.assertEqual(summary["coverage"], 1.0)
        self.assertEqual(summary["forbidden_hits"], 0)
        self.assertEqual(summary["refusal_accuracy"], 1.0)

    def test_forbidden(self) -> None:
        gold = [{"id": "a", "answer_points": [], "forbidden": ["all patients benefit"]}]
        answers = [{"id": "a", "answer": "All patients benefit [P1]."}]
        summary = eval_answers(gold, answers)["summary"]
        self.assertEqual(summary["forbidden_hits"], 1)


if __name__ == "__main__":
    unittest.main()
