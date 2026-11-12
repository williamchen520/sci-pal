"""Stable retrieval result contract for experiments and API adapters.

The system still has several backends (sentence hybrid, unified retriever,
paper-level hybrid search). Experiments must not depend on their private dict
shapes, so every adapter exposes the same hit fields:

    unit_id
    paper_id
    hit_sentence_ids      sentences that were actually scored
    context_sentence_ids  sentences added only for generation
    score
    source
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass
class RetrievalHit:
    unit_id: str
    paper_id: str
    hit_sentence_ids: list[str] = field(default_factory=list)
    context_sentence_ids: list[str] = field(default_factory=list)
    score: float = 0.0
    source: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    query: str
    hits: list[RetrievalHit] = field(default_factory=list)
    backend: str = ""
    sufficient: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "backend": self.backend,
            "sufficient": self.sufficient,
            "reason": self.reason,
            "hits": [hit.to_dict() for hit in self.hits],
        }

    def sentence_ids(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for hit in self.hits:
            for sentence_id in hit.hit_sentence_ids:
                if sentence_id not in seen:
                    seen.add(sentence_id)
                    ordered.append(sentence_id)
        return ordered


def hit_from_sentence_unit(unit: dict[str, Any], *, source: str = "sentence_backend") -> RetrievalHit:
    """Convert a sentence unit (``SentenceHybridRetriever.search``) to a hit."""
    sentence_id = str(unit.get("sentence_id") or "")
    context = [
        str(row.get("sentence_id"))
        for row in unit.get("window_sentences") or []
        if row.get("sentence_id")
    ]
    return RetrievalHit(
        unit_id=sentence_id,
        paper_id=str(unit.get("paper_id") or ""),
        hit_sentence_ids=[sentence_id] if sentence_id else [],
        context_sentence_ids=context,
        score=float(unit.get("anchor_score") or 0.0),
        source=source,
        text=str(unit.get("text") or unit.get("anchor_text") or ""),
    )


def result_from_sentence_units(
    query: str,
    units: Iterable[dict[str, Any]],
    *,
    source: str = "sentence_backend",
) -> RetrievalResult:
    hits = [hit_from_sentence_unit(unit, source=source) for unit in units]
    return RetrievalResult(
        query=query,
        hits=hits,
        backend=source,
        sufficient=bool(hits),
        reason=source if hits else "no_hits",
    )
