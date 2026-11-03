from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.p3_shadow_report import latest_snapshot, parse_tables, render_markdown


class P3ShadowReportTests(unittest.TestCase):
    def test_parse_tables_default_and_custom(self):
        self.assertIn(("papers", "paper_id"), parse_tables(""))
        self.assertEqual(parse_tables("papers:paper_id,sentences:sentence_id"), [
            ("papers", "paper_id"),
            ("sentences", "sentence_id"),
        ])

    def test_latest_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.db"
            new = root / "new.db"
            old.write_text("old", encoding="utf-8")
            new.write_text("new", encoding="utf-8")
            self.assertEqual(latest_snapshot(root).name, "new.db")

    def test_markdown_contains_tables_and_status(self):
        report = {
            "generated_at": "2026-11-03T00:00:00+00:00",
            "source": "snapshot.db",
            "status": "diff",
            "tables": [
                {
                    "table": "papers",
                    "sqlite_rows": 3,
                    "postgres_rows": 3,
                    "common_keys": 3,
                    "missing_in_pg": 0,
                    "extra_in_pg": 0,
                    "field_diffs": 1,
                    "status": "diff",
                }
            ],
            "fts": [],
        }
        text = render_markdown(report)
        self.assertIn("P3 Shadow Read Report", text)
        self.assertIn("| papers | 3 | 3 | 3 |", text)
        self.assertIn("**diff**", text)


if __name__ == "__main__":
    unittest.main()
