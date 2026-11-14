"""R parser tests."""

from __future__ import annotations

import unittest

from code_rag.parsers import parse_python, parse_r, parse_rmd
from code_rag.ingest import file_language

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

    def test_cross_language_edges(self) -> None:
        text = 'reticulate::source_python("tools.py")\nsystem("python run.py")'
        _, edges = parse_r(text, "Figure.6.R")
        cross = [edge for edge in edges if edge.relation == "cross_language"]
        self.assertEqual(len(cross), 2)
        self.assertTrue(all(edge.confidence == "low" for edge in cross))

    def test_python_to_r_edge(self) -> None:
        text = 'import subprocess\nsubprocess.run(["Rscript", "plot.R"])'
        _, edges = parse_python(text, "run.py")
        cross = [edge for edge in edges if edge.relation == "cross_language"]
        self.assertTrue(cross)
        self.assertIn("cross_language:plot.R", {edge.dst_unit_id for edge in cross})

    def test_comment_braces(self) -> None:
        units, _ = parse_r(R, "Figure.1.R")
        fn = next(unit for unit in units if unit.symbol_name == "normalize")
        self.assertIn("x / sum(x)", fn.text)
        self.assertTrue(fn.text.rstrip().endswith("}"))


RMD = """
---
title: test
---
```{r setup, include=FALSE}
library(Seurat)
norm <- function(x) { x / sum(x) }
```
```{python label=plot}
print("hi")
```
"""


class RmdParserTests(unittest.TestCase):
    def test_chunks(self) -> None:
        units, edges = parse_rmd(RMD, "analysis.Rmd")
        chunks = [unit for unit in units if unit.unit_type == "chunk"]
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].symbol_name, "setup")
        self.assertIn("library(Seurat)", chunks[0].text)
        child = next(unit for unit in units if unit.symbol_name == "norm")
        self.assertEqual(child.unit_type, "function")
        self.assertEqual(child.parent_unit_id, chunks[0].unit_id)
        self.assertEqual(chunks[1].symbol_name, "plot")
        self.assertIn("print", chunks[1].text)
        self.assertEqual(edges, [])

    def test_file_language(self) -> None:
        from pathlib import Path
        self.assertEqual(file_language(Path("a.py")), "python")
        self.assertEqual(file_language(Path("a.R")), "r")
        self.assertEqual(file_language(Path("a.Rmd")), "rmd")
        self.assertEqual(file_language(Path("a.qmd")), "rmd")
        self.assertEqual(file_language(Path("main.nf")), "nextflow")


if __name__ == "__main__":
    unittest.main()
