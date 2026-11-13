"""C3 context package tests."""

from __future__ import annotations

import unittest

from code_rag.context import parse_imports


class ContextBuilderTests(unittest.TestCase):
    def test_extracts_imports(self) -> None:
        lines = parse_imports("import scanpy as sc\nfrom .foo import bar\n\ndef f():\n    pass\n")
        self.assertEqual(lines, ["import scanpy as sc", "from .foo import bar"])

    def test_bad_source_returns_empty(self) -> None:
        self.assertEqual(parse_imports("def broken(:\n"), [])


if __name__ == "__main__":
    unittest.main()
