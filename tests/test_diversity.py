from __future__ import annotations

import unittest

from services.search.diversity import diversity_report, select_diverse


class DiversityTests(unittest.TestCase):
    def test_soft_cap_limits_one_paper(self):
        items = [
            {"para_id": f"p{i}", "paper_id": "a", "text": f"alpha beta gamma {i}", "score": 10 - i}
            for i in range(4)
        ]
        selected = select_diverse(items, top_k=10, max_per_paper=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual({item["paper_id"] for item in selected}, {"a"})

    def test_prefers_other_paper_under_cap(self):
        items = [
            {"para_id": "a1", "paper_id": "a", "text": "alpha beta gamma delta", "score": 10},
            {"para_id": "a2", "paper_id": "a", "text": "alpha beta gamma epsilon", "score": 9},
            {"para_id": "b1", "paper_id": "b", "text": "zeta eta theta iota", "score": 8},
        ]
        selected = select_diverse(items, top_k=2, max_per_paper=1)
        self.assertEqual([item["para_id"] for item in selected], ["a1", "b1"])

    def test_report(self):
        selected = [
            {"paper_id": "a"},
            {"paper_id": "a"},
            {"paper_id": "b"},
        ]
        report = diversity_report(selected)
        self.assertEqual(report["distinct_papers"], 2)
        self.assertEqual(report["max_hits_per_paper"], 2)


if __name__ == "__main__":
    unittest.main()
