"""guard 评估场景作为回归测试（合成词表，不依赖 47k 真实词表与真实 FTS）。"""

from __future__ import annotations

import unittest

from services.quality.guard import VocabularyGuard
from services.quality.lexicon import Entry, Lexicon

from scripts.eval_guard import SCENARIOS


class GuardScenarioRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        entries = [
            Entry("Gene", "HGNC:11850", "TLR4", (), 0, 0, "hgnc", "hgnc"),
            Entry("Gene", "HGNC:16400", "NLRP3", (), 0, 0, "hgnc", "hgnc"),
            Entry("Gene", "HGNC:3236", "EGFR", (), 0, 0, "hgnc", "hgnc"),
            Entry("Gene", "HGNC:11364", "STAT3", (), 0, 0, "hgnc", "hgnc"),
            Entry("Disease", "D018805", "Sepsis", (), 10, 5, "ncbi_mesh"),
            Entry("Disease", "D007249", "inflammatory", (), 50, 20, "ncbi_mesh"),
        ]
        self.lexicon = Lexicon(entries=entries)
        self.lexicon._build_index()
        self.guard = VocabularyGuard(
            self.lexicon, fts_lookup=lambda term: term.upper() == "CRISPR"
        )

    def test_all_scenarios_match_expected_unknown_counts(self) -> None:
        for name, (text, expected) in SCENARIOS.items():
            report = self.guard.check(text)
            with self.subTest(scenario=name):
                for key, value in expected.items():
                    self.assertEqual(getattr(report, key), value, name)


if __name__ == "__main__":
    unittest.main()
