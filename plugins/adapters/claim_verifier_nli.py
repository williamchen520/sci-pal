"""Adapter A0: existing LLM NLI classifier."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.claims import nli
from services.plugins.claim_contracts import (
    ClaimInput,
    ClaimVerification,
    ClaimVerifierAdapter,
    EvidenceInput,
)


class LLMClaimVerifier(ClaimVerifierAdapter):
    name = "claim-verifier-nli"
    version = "0.1.0"

    def __init__(self, llm_client: Any = None):
        if llm_client is None:
            try:
                from services.review.llm_client import create_llm_client

                llm_client = create_llm_client()
            except Exception:  # noqa: BLE001 - adapter must load without a provider
                llm_client = None
        self.llm_client = llm_client

    def verify(
        self,
        claim: ClaimInput,
        evidence: List[EvidenceInput],
        *,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerification]:
        model = str(getattr(self.llm_client, "model", "") or "llm-nli")
        results: List[ClaimVerification] = []
        for item in evidence:
            raw = nli.classify(claim.text, item.quote, llm_client=self.llm_client)
            results.append(
                ClaimVerification(
                    evidence_id=item.evidence_id,
                    relation=raw["relation"],
                    confidence=float(raw.get("confidence") or 0.0),
                    rationale=str(raw.get("reason") or ""),
                    model=model,
                )
            )
        return results
