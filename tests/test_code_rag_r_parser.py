"""R parser tests."""

from __future__ import annotations

import unittest

from code_rag.parsers import parse_r

R = """
library(Seurat)
require(harmony)
source("utils.R")

normalize <- function(x, target = 1e4) {
  # a comment with a } must not close the block
  x / sum(x) * target
}

setClass("Example", slots = list(x = "numeric"))
R6Thing <- R6Class("Thing", public = list(run = function() 1))
"""


class RParserTests(unittest.TestCase):
    def test_units(self) -> None:
        units, edges = parse_r(R, "Figure.1.R")
        kinds = {unit.unit_type for unit in units}
        self.assertIn("file", kinds)
        self.assertIn("function", kinds)
        self.assertIn("class", kinds)
        self.assertIn("setClass", kinds)
        names = {unit.symbol_name for unit in units}
        self.assertIn("normalize", names)

    def test_imports(self) -> None:
        _, edges = parse_r(R, "Figure.1.R")
        targets = {edge.dst_unit_id for edge in edges}
        self.assertIn("unresolved:library:Seurat", targets)
        self.assertIn("unresolved:library:harmony", targets)
        self.assertIn("source:utils.R", targets)

    def test_comment_braces(self) -> None:
        units, _ = parse_r(R, "Figure.1.R")
        fn = next(unit for unit in units if unit.symbol_name == "normalize")
        self.assertIn("x / sum(x)", fn.text)
        self.assertTrue(fn.text.rstrip().endswith("}"))


if __name__ == "__main__":
    unittest.main()
