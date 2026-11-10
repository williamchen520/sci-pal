"""Tests for scripts/sql_guard.py.  # sql_guard: allow-file"""

from __future__ import annotations

import unittest

from scripts.sql_guard import analyze_text


class SqlGuardTests(unittest.TestCase):
    def test_unqualified_drop_is_rejected(self) -> None:
        findings = analyze_text("DROP TABLE papers;", allow_destructive=True)
        self.assertTrue(any("not schema-qualified" in f.rule for f in findings))

    def test_qualified_drop_requires_allow(self) -> None:
        findings = analyze_text("DROP TABLE scifact_eval.papers;", allow_destructive=False)
        self.assertTrue(any("allow-destructive" in f.rule for f in findings))
        self.assertEqual(analyze_text("DROP TABLE scifact_eval.papers;", allow_destructive=True), [])

    def test_multi_table_drop_is_rejected(self) -> None:
        findings = analyze_text(
            "DROP TABLE scifact_eval.papers, scifact_eval.paragraphs CASCADE;",
            allow_destructive=True,
        )
        self.assertTrue(any("only one table" in f.rule for f in findings))

    def test_unqualified_truncate_is_rejected(self) -> None:
        findings = analyze_text("TRUNCATE TABLE papers;", allow_destructive=True)
        self.assertTrue(any("not schema-qualified" in f.rule for f in findings))

    def test_unqualified_alter_is_rejected(self) -> None:
        findings = analyze_text("ALTER TABLE papers ADD COLUMN x text;")
        self.assertTrue(any("not schema-qualified" in f.rule for f in findings))

    def test_forbidden_schema(self) -> None:
        findings = analyze_text(
            "DROP TABLE public.papers;",
            allow_destructive=True,
            forbid_schema="public",
        )
        self.assertTrue(any("forbidden" in f.rule for f in findings))

    def test_drop_database_requires_allow(self) -> None:
        findings = analyze_text("DROP DATABASE scipal_bench;")
        self.assertTrue(any("allow-destructive" in f.rule for f in findings))

    def test_allow_line(self) -> None:
        findings = analyze_text("# sql_guard: allow\nDROP TABLE papers;", allow_destructive=True)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
