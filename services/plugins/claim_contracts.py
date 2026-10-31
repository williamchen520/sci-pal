"""Typed contracts for claim verification plugins (M1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol

RELATIONS = {"supports", "refutes", "mentions", "underdetermines"}


@dataclass(frozen=True)
class ClaimInput:
    claim_id: str
    text: str
    qualifiers: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaimInput":
        if not isinstance(data, dict) or not data.get("text"):
            raise ValueError("claim must contain text")
        return cls(
            claim_id=str(data.get("claim_id") or ""),
            text=str(data["text"]),
            qualifiers=data.get("qualifiers") or {},
        )


@dataclass(frozen=True)
class EvidenceInput:
    evidence_id: str
    quote: str
    paper_id: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceInput":
        if not isinstance(data, dict) or not data.get("quote"):
            raise ValueError("evidence must contain quote")
        return cls(
            evidence_id=str(data.get("evidence_id") or ""),
            quote=str(data["quote"]),
            paper_id=str(data.get("paper_id") or ""),
        )


@dataclass(frozen=True)
class ClaimVerification:
    evidence_id: str
    relation: str
    confidence: float
    rationale: str
    model: str = ""

    def __post_init__(self) -> None:
        if self.relation not in RELATIONS:
            raise ValueError(f"invalid relation: {self.relation}")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be 0..1")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ClaimVerifierPort(Protocol):
    name: str
    version: str

    def verify(
        self,
        claim: ClaimInput,
        evidence: List[EvidenceInput],
        *,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerification]:
        ...


class ClaimVerifierAdapter:
    """Bridge a typed verifier into the generic plugin ``run`` contract."""

    name = "claim-verifier"
    version = "0.1.0"

    def verify(
        self,
        claim: ClaimInput,
        evidence: List[EvidenceInput],
        *,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[ClaimVerification]:
        raise NotImplementedError

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        claim = ClaimInput.from_dict(payload.get("claim") or {})
        evidence = [
            EvidenceInput.from_dict(item) for item in (payload.get("evidence") or [])
        ]
        if not evidence:
            raise ValueError("at least one evidence item is required")
        results = self.verify(claim, evidence, options=payload.get("options") or {})
        return {"verifications": [item.to_dict() for item in results]}
