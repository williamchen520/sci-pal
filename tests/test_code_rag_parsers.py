"""Parser tests for code-rag P2."""

from __future__ import annotations

import unittest

from code_rag.parsers import parse_nextflow, parse_python


class CodeRagParserTests(unittest.TestCase):
    def test_python_units_and_edges(self) -> None:
        source = '''\nimport scanpy as sc\n\nclass Plotter:\n    def umap(self, adata):\n        return sc.pl.umap(adata)\n'''
        units, edges = parse_python(source, "plotter.py")
        kinds = {unit.unit_type for unit in units}
        names = {unit.symbol_name for unit in units}
        self.assertIn("file", kinds)
        self.assertIn("class", kinds)
        self.assertIn("function", kinds)
        self.assertIn("Plotter", names)
        self.assertIn("umap", names)
        self.assertTrue(any(edge.relation == "imports" for edge in edges))
        self.assertTrue(any(edge.relation == "calls" for edge in edges))

    def test_nextflow_blocks_and_include(self) -> None:
        source = '''\ninclude { FASTQC } from './modules/fastqc'\n\nprocess FASTQC {\n  input:\n  path reads\n  script:\n  """\n  fastqc ${reads}\n  """\n}\n\nworkflow {\n  FASTQC()\n}\n'''
        units, edges = parse_nextflow(source, "main.nf")
        names = {unit.symbol_name for unit in units}
        types = {unit.unit_type for unit in units}
        self.assertIn("FASTQC", names)
        self.assertIn("process", types)
        self.assertIn("workflow", types)
        self.assertTrue(any(edge.relation == "imports" for edge in edges))


if __name__ == "__main__":
    unittest.main()
