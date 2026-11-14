"""Paper module map tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import modules


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Conn:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=()):
        self.sql.append(sql)
        if "FROM code_rag.code_files" in sql:
            return _Cursor([("f1", "Figure.1.R", "r")])
        if "symbol_name" in sql:
            return _Cursor([("Figure.1.R",)])
        if "SELECT text FROM code_rag.code_units" in sql:
            return _Cursor([("RunHarmony(x, group.by.vars='orig.ident')",)])
        if "SELECT DISTINCT dst_unit_id" in sql:
            return _Cursor([("unresolved:library:Seurat",), ("unresolved:library:harmony",)])
        if "SELECT relation" in sql:
            return _Cursor([("imports", 12)])
        return _Cursor([])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ModuleTests(unittest.TestCase):
    def test_unbound(self) -> None:
        with mock.patch.object(modules, "list_bindings", return_value=[]):
            result = modules.paper_modules("p1")
        self.assertEqual(result["status"], "unbound")
        self.assertEqual(result["modules"], [])

    def test_module_map(self) -> None:
        conn = _Conn()
        with mock.patch.object(modules, "list_bindings", return_value=[
            {"library_id": "lib_1", "snapshot_id": "snap_1"}
        ]), mock.patch.object(modules, "_code_connection", return_value=conn):
            result = modules.paper_modules("p1")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["modules"][0]["path"], "Figure.1.R")
        self.assertEqual(result["modules"][0]["edges"]["imports"], 12)
        self.assertIn("Seurat", result["modules"][0]["imports"])
        self.assertEqual(result["modules"][0]["purpose_source"], "inferred")
        self.assertIn("batch integration", result["modules"][0]["purpose"])
        self.assertEqual(result["modules"][0]["purpose_evidence"][0]["label"], "batch integration")
        self.assertEqual(result["modules"][0]["purpose_confidence"], "low")


if __name__ == "__main__":
    unittest.main()
