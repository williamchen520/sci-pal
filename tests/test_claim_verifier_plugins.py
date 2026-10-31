"""M1 claim-verifier adapter tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.adapters.claim_verifier_nli import LLMClaimVerifier
from plugins.adapters.claim_verifier_rule import RuleClaimVerifier
from plugins.adapters.claim_verifier_underdetermines import UnderdeterminesVerifier
from services.plugins import PluginRegistry, PluginRunner
from services.plugins.claim_contracts import ClaimInput, EvidenceInput


class FakeUnavailableLLM:
    def is_available(self) -> bool:
        return False


class ClaimVerifierPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "runs.jsonl"
        self.registry = PluginRegistry().load()

    def test_claim_verifier_plugins_are_registered(self) -> None:
        ids = [item["id"] for item in self.registry.list_plugins()]
        self.assertIn("claim-verifier-rule", ids)
        self.assertIn("claim-verifier-underdetermines", ids)
        self.assertIn("claim-verifier-nli", ids)

    def test_rule_adapter_detects_positive_and_negative(self) -> None:
        adapter = RuleClaimVerifier()
        claim = ClaimInput("c1", "drug improves survival")
        results = adapter.verify(
            claim,
            [
                EvidenceInput("e1", "The drug significantly improved survival."),
                EvidenceInput("e2", "The drug did not improve survival; no benefit."),
            ],
        )
        self.assertEqual(results[0].relation, "supports")
        self.assertEqual(results[1].relation, "refutes")

    def test_underdetermines_adapter(self) -> None:
        adapter = UnderdeterminesVerifier()
        result = adapter.verify(
            ClaimInput("c1", "claim"), [EvidenceInput("e1", "quote")]
        )[0]
        self.assertEqual(result.relation, "underdetermines")
        self.assertEqual(result.confidence, 0.0)

    def test_nli_adapter_without_provider(self) -> None:
        adapter = LLMClaimVerifier(llm_client=FakeUnavailableLLM())
        result = adapter.verify(
            ClaimInput("c1", "claim"), [EvidenceInput("e1", "quote")]
        )[0]
        self.assertEqual(result.relation, "underdetermines")
        self.assertIn("LLM unavailable", result.rationale)

    def test_runner_validates_claim_verifier_output(self) -> None:
        runner = PluginRunner(self.registry, run_log=self.log)
        run = runner.run(
            "claim-verifier-rule",
            {
                "claim": {"claim_id": "c1", "text": "drug improves survival"},
                "evidence": [{"evidence_id": "e1", "quote": "significantly improved"}],
            },
            dataset_hash="sha256:test",
        )
        self.assertEqual(run.output["verifications"][0]["relation"], "supports")
        self.assertTrue(self.log.exists())


if __name__ == "__main__":
    unittest.main()
