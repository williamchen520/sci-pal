"""Architecture contract guard tests for module-boundary rules."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import scripts.guard as guard


class ForbidImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._old_root = guard.ROOT
        guard.ROOT = self.root

    def tearDown(self) -> None:
        guard.ROOT = self._old_root

    def _write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _run(self, rule: dict) -> list[dict]:
        return guard.check_forbid_import(rule, SimpleNamespace(staged=False, base_ref=""))

    def test_forbidden_module_is_reported(self) -> None:
        self._write("services/qa/qa.py", "import sqlite3\n")
        rule = {
            "params": {
                "scope": "services/qa/**/*.py",
                "modules": ["sqlite3"],
                "only_new": False,
            }
        }
        self.assertEqual(len(self._run(rule)), 1)

    def test_forbidden_symbol_is_reported(self) -> None:
        self._write(
            "services/qa/qa.py",
            "from services.review.evidence_extractor import EvidenceExtractor\n",
        )
        rule = {
            "params": {
                "scope": "services/qa/**/*.py",
                "modules": ["services.review.evidence_extractor"],
                "names": ["EvidenceExtractor"],
                "only_new": False,
            }
        }
        self.assertEqual(len(self._run(rule)), 1)

    def test_clean_file_passes(self) -> None:
        self._write("services/qa/qa.py", "from services.retrieval import retrieve\n")
        rule = {
            "params": {
                "scope": "services/qa/**/*.py",
                "modules": ["services.review.evidence_extractor"],
                "names": ["EvidenceExtractor"],
                "only_new": False,
            }
        }
        self.assertEqual(self._run(rule), [])

    def test_contract_has_five_boundary_rules(self) -> None:
        contract = guard.load_contract()
        ids = {rule["id"] for rule in contract["rules"]}
        for rule_id in (
            "review-no-storage",
            "qa-no-evidence-extractor",
            "downloader-no-llm",
            "search-no-review-generator",
            "no-direct-data-db",
        ):
            self.assertIn(rule_id, ids)


if __name__ == "__main__":
    unittest.main()
