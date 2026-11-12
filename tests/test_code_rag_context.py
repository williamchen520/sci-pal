"""E3 import parsing tests."""

from __future__ import annotations

import unittest

from eval.code_rag_stack.e3_context import parse_imports


class ContextImportTests(unittest.TestCase):
    def test_parses_imports_and_aliases(self) -> None:
        lines, aliases = parse_imports(
            "import scanpy as sc\nfrom .foo import bar as baz\n\ndef f():\n    return sc, baz\n"
        )
        self.assertEqual(len(lines), 2)
        self.assertIn(("sc", "import scanpy as sc"), aliases)
        self.assertIn(("baz", "from .foo import bar as baz"), aliases)

    def test_bad_source_returns_empty(self) -> None:
        lines, aliases = parse_imports("def broken(:\n")
        self.assertEqual(lines, [])
        self.assertEqual(aliases, [])


if __name__ == "__main__":
    unittest.main()
