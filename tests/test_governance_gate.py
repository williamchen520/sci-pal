"""Tests for the deterministic governance preflight gate."""

from __future__ import annotations

import unittest

from scripts.governance_gate import check, format_block, main


class GovernanceGateTests(unittest.TestCase):
    def test_physical_moat_is_blocked(self) -> None:
        result = check(paths=["services/db/pg_pool.py"])
        self.assertTrue(result["blocked"])
        self.assertIn("physical_moat", {hit["id"] for hit in result["triggers"]})

    def test_docs_only_is_allowed(self) -> None:
        result = check(paths=["docs/README.md"])
        self.assertFalse(result["blocked"])

    def test_contract_change_is_blocked(self) -> None:
        result = check(paths=["routes/papers.py"])
        self.assertTrue(result["blocked"])
        self.assertIn("contract_lock", {hit["id"] for hit in result["triggers"]})

    def test_large_change_is_blocked(self) -> None:
        self.assertTrue(check(lines=301)["blocked"])
        self.assertFalse(check(lines=300)["blocked"])

    def test_confirmatory_experiment_is_blocked(self) -> None:
        result = check(paths=["eval/run.py"], ops=["confirmatory_experiment"])
        self.assertTrue(result["blocked"])
        self.assertIn("orthogonal_control", {hit["id"] for hit in result["triggers"]})

    def test_hard_cut_operation_is_blocked(self) -> None:
        result = check(ops=["hard_cut_500w"])
        self.assertTrue(result["blocked"])
        self.assertIn("dimensional_adaptation", {hit["id"] for hit in result["triggers"]})

    def test_warning_requires_human_approval_phrase(self) -> None:
        result = check(paths=["services/db/pg_pool.py"])
        message = format_block(result, plan="改连接", risk="可能串库")
        self.assertIn("批准执行", message)
        self.assertIn("物理护城河", message)

    def test_cli_exit_code_blocks(self) -> None:
        self.assertEqual(main(["--paths", "services/db/pg_pool.py", "--json"]), 2)


if __name__ == "__main__":
    unittest.main()
