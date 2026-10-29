"""Sentence role scoring tests."""

from __future__ import annotations

import unittest

from services.search.sentence_roles import classify_sentence, pick_anchor, score_sentence


class SentenceRoleTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_sentence("ORR was 42% (p=0.01)."), "result")
        self.assertEqual(classify_sentence("A key limitation is the small sample."), "limitation")
        self.assertEqual(classify_sentence("Patients were randomized to receive 5 mg."), "method")

    def test_result_beats_background(self) -> None:
        sentences = [
            {"text": "ICI is a treatment for HCC."},
            {"text": "The response rate was 42% (p=0.01)."},
        ]
        self.assertIn("42%", pick_anchor(sentences, "What was the response rate?")["text"])

    def test_numeric_bonus(self) -> None:
        self.assertGreater(
            score_sentence("Response 42%.", {"response"}, "results"),
            score_sentence("Response was observed.", {"response"}, "results"),
        )


if __name__ == "__main__":
    unittest.main()
