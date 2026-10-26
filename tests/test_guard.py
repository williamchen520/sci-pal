"""scipal-guard P1 tests (synthetic lexicon + fake FTS)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.quality.guard import VocabularyGuard
from services.quality.lexicon import Lexicon, normalize_surface

HEADER = "type\tnormalized_id\tdatabase\tcanonical\taliases\tmentions\tpapers\n"


def write_lexicon(path: Path) -> None:
    rows = [
        "Gene\t1956\tncbi_gene\tEGFR\tERBB; HER1\t20\t5",
        "Gene\t6774\tncbi_gene\tSTAT3\t\t10\t3",
        "Gene\t20848\tncbi_gene\tSTAT3\t\t4\t2",  # same surface, different id -> ambiguous
        "Disease\tD009369\tncbi_mesh\ttumor\tcancer\t100\t40",
        "Chemical\tD000001\tncbi_mesh\tDMSO\t\t1\t1",  # weak (single paper)
    ]
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")


class NormalizationTests(unittest.TestCase):
    def test_normalize_handles_case_greek_and_separators(self) -> None:
        self.assertEqual(normalize_surface("NF-kappaB"), "nf kappab")
        self.assertEqual(normalize_surface("TNF-α"), "tnf alpha")
        self.assertEqual(normalize_surface("  IL-6 "), "il 6")


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "lex.tsv"
        write_lexicon(path)
        self.lexicon = Lexicon.load(path)
        self.fts = {"CAS9": True}

    def guard(self) -> VocabularyGuard:
        return VocabularyGuard(self.lexicon, fts_lookup=lambda term: self.fts.get(term.upper(), False))

    def test_known_ambiguous_broad_and_unknown(self) -> None:
        report = self.guard().check("EGFR and STAT3 drive tumor growth, FOOBARX is novel.")
        statuses = {(issue.term.upper(), issue.status) for issue in report.issues}
        self.assertIn(("EGFR", "known_curated"), statuses)
        self.assertIn(("STAT3", "ambiguous"), statuses)
        self.assertIn(("TUMOR", "known_broad"), statuses)
        self.assertIn(("FOOBARX", "unknown"), statuses)
        self.assertEqual(report.counts["unknown"], 1)

    def test_corpus_landing_silences_method_terms(self) -> None:
        report = self.guard().check("We used CAS9 editing and FOOBARX.")
        statuses = {issue.term.upper(): issue.status for issue in report.issues}
        self.assertEqual(statuses.get("CAS9"), "corpus")
        self.assertEqual(statuses.get("FOOBARX"), "unknown")

    def test_defined_abbreviation_is_not_flagged(self) -> None:
        report = self.guard().check(
            "Epidermal growth factor receptor (EGFR) was measured; XYZQ appears."
        )
        terms = {issue.term.upper(): issue.status for issue in report.issues}
        self.assertNotEqual(terms.get("EGFR"), "undefined_abbrev")

    def test_unknown_ratio(self) -> None:
        report = self.guard().check("EGFR STAT3 tumor FOOBARX")
        self.assertGreater(report.unknown_ratio, 0.0)
        self.assertLessEqual(report.unknown_ratio, 1.0)
        summary = report.summary()
        self.assertIn("counts", summary)
        self.assertLessEqual(len(summary["issues"]), 50)


if __name__ == "__main__":
    unittest.main()
