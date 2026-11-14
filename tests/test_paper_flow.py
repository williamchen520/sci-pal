"""Paper data-flow tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import flow


class FlowTests(unittest.TestCase):
    def test_extract_reads_and_writes(self) -> None:
        nodes, edges = flow._extract(
            "Figure.1.R",
            "r",
            'x <- readRDS("Our single-cell atlas.rds")\nsaveRDS(x, "Total atlas.rds")',
        )
        ids = {node["id"] for node in nodes}
        self.assertIn("artifact:Our single-cell atlas.rds", ids)
        self.assertIn("artifact:Total atlas.rds", ids)
        relations = {edge["relation"] for edge in edges}
        self.assertEqual(relations, {"reads", "writes"})

    def test_unbound(self) -> None:
        with mock.patch.object(flow, "list_bindings", return_value=[]):
            result = flow.paper_data_flow("p1")
        self.assertEqual(result["status"], "unbound")

    def test_flow_from_bound_library(self) -> None:
        with mock.patch.object(
            flow, "list_bindings", return_value=[{"library_id": "lib_1", "snapshot_id": "snap_1"}]
        ), mock.patch.object(
            flow,
            "_files",
            return_value=[("Figure.1.R", "r", 'saveRDS(x, "atlas.rds")')],
        ):
            result = flow.paper_data_flow("p1")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["edges"][0]["relation"], "writes")
        self.assertEqual(result["edges"][0]["confidence"], "explicit")


if __name__ == "__main__":
    unittest.main()
