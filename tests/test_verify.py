"""Deterministic verify_answer tests."""

from __future__ import annotations

import unittest

from services.qa.verify import verify_answer


class VerifyAnswerTests(unittest.TestCase):
    def test_ok_with_citation(self) -> None:
        report = verify_answer(
            "The response rate was 42% in the rechallenge cohort [P1].",
            evidence_ids=["P1"],
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["missing_ids"], [])

    def test_missing_evidence_id(self) -> None:
        report = verify_answer("This is supported [P9].", evidence_ids=["P1"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing_ids"], ["[P9]"])

    def test_uncited_claim(self) -> None:
        report = verify_answer(
            "This sentence is a long factual claim without any citation at all, unfortunately.",
            evidence_ids=["P1"],
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["uncited_claims"])

    def test_conflict_requires_condition(self) -> None:
        report = verify_answer(
            "The two trials conflict on efficacy [P1].",
            evidence_ids=["P1"],
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["conflict"]["structure_ok"])

    def test_quote_grounding(self) -> None:
        evidence = [{"evidence_id": "P1", "text": "Response rate was 42%."}]
        report = verify_answer(
            'The response rate was 42% [P1]. As quoted: "response rate was 42%".',
            evidence_ids=["P1"],
            evidence=evidence,
        )
        self.assertEqual(report["quote_mismatch"], [])

    def test_quote_mismatch(self) -> None:
        evidence = [{"evidence_id": "P1", "text": "Response rate was 42%."}]
        report = verify_answer(
            'The response rate was 42% [P1]. As quoted: "response rate was 99%".',
            evidence_ids=["P1"],
            evidence=evidence,
        )
        self.assertTrue(report["quote_mismatch"])


if __name__ == "__main__":
    unittest.main()
