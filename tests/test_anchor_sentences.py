from __future__ import annotations

import unittest

from services.search.anchor_sentences import score_sentence, select_anchors


class AnchorSentenceTests(unittest.TestCase):
    def test_selects_query_relevant_sentence(self):
        query = "IL-23 oncolytic vaccinia pancreatic cancer"
        sentences = [
            {"sentence_id": "s1", "text": "This paragraph introduces the methods.", "sequence": 1},
            {"sentence_id": "s2", "text": "IL-23 engineered vaccinia controls pancreatic cancer.", "sequence": 2},
            {"sentence_id": "s3", "text": "Statistical analysis was performed.", "sequence": 3},
        ]
        anchors = select_anchors(query, sentences, limit=2)
        self.assertEqual(anchors[0]["sentence_id"], "s2")
        self.assertGreater(anchors[0]["anchor_score"], 0)

    def test_existing_anchor_gets_prior(self):
        query = "immune disorder"
        sentences = [
            {"sentence_id": "s1", "text": "Unrelated sentence.", "sequence": 1},
            {"sentence_id": "s2", "text": "Mesenchymal cells modulate immune disorder.", "sequence": 2},
        ]
        anchors = select_anchors(query, sentences, existing=[{"sentence_id": "s1"}], limit=2)
        self.assertIn("s2", [row["sentence_id"] for row in anchors])

    def test_limit(self):
        sentences = [
            {"sentence_id": f"s{i}", "text": "cancer", "sequence": i}
            for i in range(10)
        ]
        self.assertEqual(len(select_anchors("cancer", sentences, limit=2)), 2)

    def test_empty_score(self):
        self.assertEqual(score_sentence("", "text"), 0.0)


if __name__ == "__main__":
    unittest.main()
