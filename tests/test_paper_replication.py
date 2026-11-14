"""Replication plan tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import replication


class ReplicationTests(unittest.TestCase):
    def test_plan(self) -> None:
        with mock.patch.object(
            replication,
            "paper_modules",
            return_value={"status": "ok", "modules": [{"path": "Figure.1.R", "language": "r"}]},
        ), mock.patch.object(
            replication,
            "paper_data_flow",
            return_value={
                "edges": [
                    {"source": "file:Figure.1.R", "target": "artifact:atlas.rds", "relation": "writes"},
                    {"source": "file:Figure.1.R", "target": "artifact:counts.rds", "relation": "reads"},
                ]
            },
        ):
            plan = replication.replication_plan("p1", "Figure.1.R")
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["inputs"], ["counts.rds"])
        self.assertEqual(plan["outputs"], ["atlas.rds"])
        self.assertFalse(plan["executed"])

    def test_missing_target(self) -> None:
        with mock.patch.object(
            replication, "paper_modules", return_value={"status": "ok", "modules": []}
        ):
            plan = replication.replication_plan("p1", "missing.R")
        self.assertEqual(plan["status"], "blocked")

    def test_unbound(self) -> None:
        with mock.patch.object(
            replication, "paper_modules", return_value={"status": "unbound", "modules": []}
        ):
            plan = replication.replication_plan("p1", "Figure.1.R")
        self.assertEqual(plan["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
