"""Sentence-hybrid evidence bundle adapter tests."""

from __future__ import annotations

import unittest

from services.search.sentence_hybrid import SentenceHybridRetriever


class SentenceEvidenceAdapterTests(unittest.TestCase):
    def _retriever(self):
        retriever = object.__new__(SentenceHybridRetriever)
        retriever.search = lambda query, top_k=10: [
            {
                "sentence_id": "paper_PMC1_para_00001_sent_002",
                "para_id": "paper_PMC1_para_00001",
                "paper_id": "paper_PMC1",
                "anchor_text": "Response rate was 42%.",
                "anchor_score": 0.9,
                "context_mode": "logical_window",
                "context_scored": False,
                "window_sentences": [
                    {"sentence_id": "paper_PMC1_para_00001_sent_002", "text": "Response rate was 42%."}
                ],
                "text": "However, response rate was 42%.",
                "paragraph_text": "However, response rate was 42%.",
            }
        ]
        return retriever

    def test_bundle_is_compatible_with_evidence_route(self) -> None:
        bundle = self._retriever().to_evidence_json("response rate", top_paragraphs=5)
        self.assertTrue(bundle["sufficient"])
        self.assertEqual(len(bundle["evidence"]), 1)
        item = bundle["evidence"][0]
        self.assertEqual(item["paper_id"], "paper_PMC1")
        self.assertEqual(item["highlight"][0]["sentence_id"], "paper_PMC1_para_00001_sent_002")
        self.assertEqual(item["paragraph_details"][0]["sentence_ids"], ["paper_PMC1_para_00001_sent_002"])

    def test_window_is_not_marked_as_scored(self) -> None:
        retriever = object.__new__(SentenceHybridRetriever)
        retriever.search = lambda query, top_k=10: [
            {
                "sentence_id": "s1",
                "para_id": "p1",
                "paper_id": "paper1",
                "anchor_text": "anchor",
                "window_sentences": [{"sentence_id": "s1", "text": "anchor"}],
                "text": "anchor",
            }
        ]
        bundle = retriever.to_evidence_json("q")
        item = bundle["evidence"][0]
        self.assertEqual(item["text"], "anchor")
        self.assertNotIn("context_scored", item)


if __name__ == "__main__":
    unittest.main()
