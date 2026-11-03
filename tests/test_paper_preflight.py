from __future__ import annotations

import unittest

from services.papers import preflight


class PreflightTests(unittest.TestCase):
    def test_repairs_ids_and_drops_empty_paragraphs(self):
        parsed = {
            "metadata": {"title": ""},
            "paragraphs": [
                {"para_id": "p1", "text": "first", "sequence": 0},
                {"para_id": "p1", "text": "second", "sequence": 1},
                {"para_id": "", "text": "", "sequence": 2},
            ],
        }
        report = preflight.audit_and_repair(parsed, "paper_x", "test")
        self.assertTrue(report.ok)
        self.assertEqual(len(parsed["paragraphs"]), 2)
        ids = [row["para_id"] for row in parsed["paragraphs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any("duplicate" in item for item in report.repairs))
        self.assertEqual(parsed["metadata"]["title"], "Untitled")

    def test_dangling_section_parent_is_dropped(self):
        parsed = {
            "paragraphs": [{"para_id": "p1", "text": "text"}],
            "sections": [
                {"section_id": "s1", "parent_id": "missing", "level": 1, "title": "T"}
            ],
        }
        report = preflight.audit_and_repair(parsed, "paper_x", "test")
        self.assertTrue(report.ok)
        self.assertIsNone(parsed["sections"][0]["parent_id"])
        self.assertTrue(any("dangling" in item for item in report.warnings))

    def test_missing_paper_id_is_error(self):
        report = preflight.audit_and_repair({"paragraphs": []}, None, "test")
        self.assertFalse(report.ok)
        self.assertIn("missing paper_id", report.errors)
        with self.assertRaises(preflight.PreflightError):
            preflight.require_ok(report)

    def test_disabled_flag(self):
        import os

        old = os.environ.get("SCIPAL_INGEST_PREFLIGHT")
        os.environ["SCIPAL_INGEST_PREFLIGHT"] = "0"
        try:
            self.assertFalse(preflight.enabled())
        finally:
            if old is None:
                os.environ.pop("SCIPAL_INGEST_PREFLIGHT", None)
            else:
                os.environ["SCIPAL_INGEST_PREFLIGHT"] = old


if __name__ == "__main__":
    unittest.main()
