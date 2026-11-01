from __future__ import annotations

import os
import unittest
from unittest import mock

from services.search.dedup import (
    jaccard,
    normalize_text,
    shingles,
    suppress_near_duplicates,
    threshold_from_env,
)


class DedupTests(unittest.TestCase):
    def test_normalize_and_shingles(self):
        self.assertEqual(normalize_text("  A  B\nC "), "a b c")
        self.assertTrue(shingles("one two three four"))

    def test_exact_duplicate_keeps_highest_score(self):
        items = [
            {"para_id": "p1", "paper_id": "paper-a", "text": "same text", "score": 0.5},
            {"para_id": "p2", "paper_id": "paper-a", "text": "same text", "score": 0.9},
        ]
        out = suppress_near_duplicates(items, threshold=0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["score"], 0.9)

    def test_same_id_is_removed_even_with_different_text(self):
        items = [
            {"sentence_id": "s1", "paper_id": "paper-a", "text": "first", "score": 0.9},
            {"sentence_id": "s1", "paper_id": "paper-a", "text": "second", "score": 0.8},
        ]
        out = suppress_near_duplicates(items, threshold=0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "first")

    def test_same_paper_near_duplicate_is_removed(self):
        base = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
        altered = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda nu"
        items = [
            {"para_id": "p1", "paper_id": "paper-a", "text": base, "score": 0.9},
            {"para_id": "p2", "paper_id": "paper-a", "text": altered, "score": 0.8},
        ]
        out = suppress_near_duplicates(items, threshold=0.8)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["para_id"], "p1")

    def test_different_papers_are_not_near_collapsed(self):
        base = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
        altered = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda nu"
        items = [
            {"para_id": "p1", "paper_id": "paper-a", "text": base, "score": 0.9},
            {"para_id": "p2", "paper_id": "paper-b", "text": altered, "score": 0.8},
        ]
        out = suppress_near_duplicates(items, threshold=0.5)
        self.assertEqual(len(out), 2)

    def test_exact_text_across_papers_is_removed(self):
        items = [
            {"para_id": "p1", "paper_id": "paper-a", "text": "same", "score": 0.9},
            {"para_id": "p2", "paper_id": "paper-b", "text": "same", "score": 0.8},
        ]
        out = suppress_near_duplicates(items, threshold=0.9)
        self.assertEqual(len(out), 1)

    def test_max_per_paper(self):
        items = [
            {"paper_id": "a", "text": "one", "score": 0.9},
            {"paper_id": "a", "text": "two", "score": 0.8},
            {"paper_id": "b", "text": "three", "score": 0.7},
        ]
        out = suppress_near_duplicates(items, threshold=0, max_per_paper=1)
        self.assertEqual([item["paper_id"] for item in out], ["a", "b"])

    def test_threshold_from_env(self):
        with mock.patch.dict(os.environ, {"SCIPAL_NEAR_DUP_THRESHOLD": "0.85"}):
            self.assertEqual(threshold_from_env(), 0.85)
        with mock.patch.dict(os.environ, {"SCIPAL_NEAR_DUP_THRESHOLD": "bad"}):
            self.assertEqual(threshold_from_env(), 0.0)

    def test_jaccard_bounds(self):
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertEqual(jaccard({"a"}, {"a"}), 1.0)
        self.assertEqual(jaccard({"a"}, {"b"}), 0.0)


if __name__ == "__main__":
    unittest.main()
