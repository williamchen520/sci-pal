"""Sentence tree tests."""

from __future__ import annotations

import unittest

from services.papers.sentences import paragraph_sentences, split_sentences


class SentenceTreeTests(unittest.TestCase):
    def test_scientific_abbreviation(self) -> None:
        text = "We used 0.05 as cutoff. Expression was measured (Fig. 2). Results were stable."
        sentences = split_sentences(text)
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences[0]["text"], "We used 0.05 as cutoff.")

    def test_offsets_cover_text(self) -> None:
        text = "First sentence. Second sentence."
        sentences = split_sentences(text)
        self.assertEqual(sentences[0]["char_start"], 0)
        self.assertEqual(sentences[0]["char_end"], len("First sentence."))
        self.assertGreater(sentences[1]["char_start"], sentences[0]["char_end"])

    def test_stable_sentence_ids(self) -> None:
        paragraph = {
            "para_id": "paper_1_para_00001",
            "text": "One. Two.",
            "page": 1,
            "bbox": "1,2,3,4",
            "section_id": "sec_1",
        }
        rows = paragraph_sentences("paper_1", paragraph)
        self.assertEqual(rows[0]["sentence_id"], "paper_1_para_00001_sent_001")
        self.assertEqual(rows[1]["sequence"], 2)
        self.assertEqual(rows[0]["section_id"], "sec_1")


if __name__ == "__main__":
    unittest.main()
