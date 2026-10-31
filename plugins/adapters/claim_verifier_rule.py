"""Adapter A1: deterministic keyword/direction baseline.

This is a deliberately simple baseline, not a scientific NLI model. It exists so
plugin comparison has a cheap, reproducible control.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.plugins.claim_contracts import (
    ClaimInput,
    ClaimVerification,
    ClaimVerifierAdapter,
    EvidenceInput,
)

NEGATIVE_CUES = (
    "not significant", "no significant", "no benefit", "did not", "failed",
    "not improved", "inferior", "immature", "not reached", "no difference",
    "resistance", "worse",
)
POSITIVE_CUES = (
    "improved", "significantly", "benefit", "superior", "prolonged",
    "associated with", "increased", "better",
)


class RuleClaimVerifier(ClaimVerifierAdapter):
    name = "claim-verifier-rule"
    version = "0.1.0"

    def verify(
        self,
        claim: ClaimInput,
        evidence: List[EvidenceInput],
        *,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerification]:
        results: List[ClaimVerification] = []
        for item in evidence:
            quote = item.quote.lower()
            if any(cue in quote for cue in NEGATIVE_CUES):
                relation, confidence, why = "refutes", 0.4, "negative/direction cue"
            elif any(cue in quote for cue in POSITIVE_CUES):
                relation, confidence, why = "supports", 0.35, "positive cue"
            else:
                relation, confidence, why = "underdetermines", 0.2, "no direction cue"
            results.append(
                ClaimVerification(
                    evidence_id=item.evidence_id,
                    relation=relation,
                    confidence=confidence,
                    rationale=why,
                    model=self.name,
                )
            )
        return results
