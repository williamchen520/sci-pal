"""Adapter A2: always-underdetermines smoke baseline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.plugins.claim_contracts import (
    ClaimInput,
    ClaimVerification,
    ClaimVerifierAdapter,
    EvidenceInput,
)


class UnderdeterminesVerifier(ClaimVerifierAdapter):
    name = "claim-verifier-underdetermines"
    version = "0.1.0"

    def verify(
        self,
        claim: ClaimInput,
        evidence: List[EvidenceInput],
        *,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerification]:
        return [
            ClaimVerification(
                evidence_id=item.evidence_id,
                relation="underdetermines",
                confidence=0.0,
                rationale="smoke baseline: always underdetermines",
                model=self.name,
            )
            for item in evidence
        ]
