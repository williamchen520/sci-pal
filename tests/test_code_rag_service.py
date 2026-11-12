"""Code RAG P1 service/manifest tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from code_rag.service import SCHEMA_VERSION, health


class _Result:
    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value


class _Conn:
    def __init__(self):
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        if "schema_version" in sql:
            return _Result((SCHEMA_VERSION,))
        if "code_units" in sql:
            return _Result((11,))
        if "code_snapshots" in sql:
            return _Result((2,))
        return _Result((1,))


class CodeRagServiceTests(unittest.TestCase):
    def test_health_reports_schema_and_counts(self) -> None:
        conn = _Conn()
        result = health(conn=conn)
        self.assertTrue(result["ok"])
        self.assertEqual(result["units"], 11)
        self.assertEqual(result["snapshots"], 2)
        self.assertEqual(result["libraries"], 1)
        self.assertEqual(conn.calls, 4)

    def test_manifest_is_independent_module(self) -> None:
        manifest = json.loads(
            Path(__file__).resolve().parent.parent.joinpath("code_rag/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["module_id"], "code")
        self.assertEqual(manifest["database"], "scipal_code")
        self.assertIn("code_search", manifest["capabilities"])


if __name__ == "__main__":
    unittest.main()
