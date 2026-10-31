"""Typed contracts for retrieval plugins (M2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class RetrieverCandidate:
    paper_id: str
    node_id: str
    text: str
    score: float
    rank: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RetrieverPort(Protocol):
    name: str
    version: str

    def retrieve(
        self,
        query: str,
        *,
        corpus: List[str],
        top_k: int = 10,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[RetrieverCandidate]:
        ...


class RetrieverAdapter:
    """Bridge a typed retriever into the generic plugin ``run`` contract."""

    name = "retriever"
    version = "0.1.0"

    def retrieve(
        self,
        query: str,
        *,
        corpus: List[str],
        top_k: int = 10,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[RetrieverCandidate]:
        raise NotImplementedError

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = str(payload.get("query") or "").strip()
        if not query:
            raise ValueError("query must not be empty")
        corpus = [str(item) for item in (payload.get("corpus") or []) if item]
        if not corpus:
            raise ValueError("corpus must not be empty")
        top_k = int(payload.get("top_k") or 10)
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be 1..100")
        results = self.retrieve(
            query,
            corpus=corpus,
            top_k=top_k,
            options=payload.get("options") or {},
        )
        return {"candidates": [item.to_dict() for item in results]}
