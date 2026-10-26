"""scipal-guard P1 tests (synthetic lexicon + fake FTS)."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
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
        self.fts = {"HEK293": True}

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
        report = self.guard().check("We used HEK293 cells and FOOBARX.")
        statuses = {issue.term.upper(): issue.status for issue in report.issues}
        self.assertEqual(statuses.get("HEK293"), "corpus")
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

    def test_known_abbreviation_is_not_unknown(self) -> None:
        report = self.guard().check("PBMC were isolated and ZZZZ was not.")
        statuses = {issue.term.upper(): issue.status for issue in report.issues}
        self.assertEqual(statuses.get("PBMC"), "known_curated")
        self.assertEqual(statuses.get("ZZZZ"), "unknown")
        detail = next(i.detail for i in report.issues if i.term.upper() == "PBMC")
        self.assertIn("peripheral blood mononuclear cell", detail)


class HgncTokenTests(unittest.TestCase):
    def test_hgnc_symbol_is_known_and_not_flagged(self) -> None:
        from services.quality.guard import VocabularyGuard
        from services.quality.lexicon import Entry, Lexicon

        lexicon = Lexicon(
            entries=[
                Entry("Gene", "hgnc:1234", "FOO1", (), 0, 0, "hgnc", "hgnc"),
                Entry("Gene", "1956", "EGFR", ("ERBB",), 20, 5, "ncbi_gene"),
            ]
        )
        lexicon._build_index()
        guard = VocabularyGuard(lexicon, fts_lookup=lambda term: False)
        report = guard.check("FOO1 and EGFR were measured.")
        statuses = {issue.term.upper(): issue.status for issue in report.issues}
        self.assertEqual(statuses.get("FOO1"), "known_curated")
        self.assertEqual(statuses.get("EGFR"), "known_curated")
        self.assertEqual(report.counts.get("unknown", 0), 0)

    def test_hgnc_row_wins_over_pubtator_duplicate(self) -> None:
        from services.quality.lexicon import Entry, Lexicon

        lexicon = Lexicon(
            entries=[
                Entry("Gene", "1956", "TLR4", (), 20, 5, "ncbi_gene"),
                Entry("Gene", "HGNC:11850", "TLR4", (), 0, 0, "hgnc", "hgnc"),
            ]
        )
        lexicon._build_index()
        preferred = lexicon.preferred("TLR4")
        self.assertEqual(len(preferred), 1)
        self.assertEqual(preferred[0].normalized_id, "HGNC:11850")

    def test_merge_does_not_duplicate_index_rows(self) -> None:
        from services.quality.lexicon import Entry, Lexicon

        pubtator = Lexicon(entries=[Entry("Gene", "1956", "EGFR", (), 20, 5, "ncbi_gene")])
        pubtator._build_index()
        hgnc = Lexicon(entries=[Entry("Gene", "HGNC:3236", "EGFR", (), 0, 0, "hgnc", "hgnc")])
        hgnc._build_index()
        pubtator.merge(hgnc)
        self.assertEqual(len(pubtator.lookup("EGFR")), 2)
        self.assertEqual(len(pubtator.preferred("EGFR")), 1)


class MeshLexiconTests(unittest.TestCase):
    def test_mesh_entries_are_curated_and_lookup_only(self) -> None:
        from services.quality.lexicon import Lexicon

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "mesh.tsv"
            path.write_text(
                HEADER
                + "Disease\tD018805\tncbi_mesh\tSepsis\tsepticemia; blood poisoning\t0\t0\n"
                + "Chemical\tD000001\tncbi_mesh\tDimethyl Sulfoxide\tDMSO\t0\t0\n",
                encoding="utf-8",
            )
            lexicon = Lexicon.load(path, source="mesh")
        self.assertEqual(lexicon.lookup("sepsis")[0].tier, "curated")
        self.assertEqual(lexicon.lookup("DMSO")[0].type, "Chemical")
        self.assertEqual(list(lexicon.match_surfaces()), [])

    def test_multiword_mesh_phrase_is_matched(self) -> None:
        from services.quality.guard import VocabularyGuard
        from services.quality.lexicon import Lexicon

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "mesh.tsv"
            path.write_text(
                HEADER
                + "Disease\tD002051\tncbi_mesh\tBurkitt Lymphoma\tBurkitt's lymphoma\t0\t0\n",
                encoding="utf-8",
            )
            lexicon = Lexicon.load(path, source="mesh")
        guard = VocabularyGuard(lexicon, fts_lookup=lambda term: False)
        report = guard.check("Burkitt lymphoma was diagnosed in two patients.")
        statuses = {issue.term.lower(): issue.status for issue in report.issues}
        self.assertEqual(statuses.get("burkitt lymphoma"), "known_curated")

    def test_unknown_multiword_phrase_is_not_flagged(self) -> None:
        from services.quality.guard import VocabularyGuard
        from services.quality.lexicon import Lexicon

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "mesh.tsv"
            path.write_text(HEADER, encoding="utf-8")
            lexicon = Lexicon.load(path, source="mesh")
        guard = VocabularyGuard(lexicon, fts_lookup=lambda term: False)
        report = guard.check("Zorblax syndrome was observed in the cohort.")
        self.assertEqual(report.counts.get("unknown", 0), 0)

    def test_brand_name_resolves_to_generic(self) -> None:
        from services.quality.guard import VocabularyGuard
        from services.quality.lexicon import Lexicon

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "brands.tsv"
            path.write_text(
                HEADER + "Chemical\tfda:atorvastatin\tfda_ndc\tatorvastatin\tLipitor\t0\t0\n",
                encoding="utf-8",
            )
            lexicon = Lexicon.load(path, source="fda")
        guard = VocabularyGuard(lexicon, fts_lookup=lambda term: False)
        report = guard.check("Lipitor reduced LDL cholesterol.")
        statuses = {issue.term: issue.status for issue in report.issues}
        self.assertEqual(statuses.get("Lipitor"), "known_curated")


class FtsLandingThreadTests(unittest.TestCase):
    def test_connection_works_across_threads(self) -> None:
        from services.quality.guard import FtsLanding

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "fts.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE VIRTUAL TABLE paragraphs_fts USING fts5(text)")
            conn.execute("INSERT INTO paragraphs_fts(text) VALUES ('TLR4 signaling in sepsis')")
            conn.commit()
            conn.close()

            landing = FtsLanding(db)
            result = []
            worker = threading.Thread(target=lambda: result.append(landing("sepsis")))
            worker.start()
            worker.join()
            self.assertEqual(result, [True])
            self.assertTrue(landing("TLR4"))


if __name__ == "__main__":
    unittest.main()
