"""Semantic claim-evidence grounding with a cross-encoder."""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Optional

from config.paths import RERANK_MODEL

CITE_RE = re.compile(r"\[[TPFRCG]\d+(?:\s*,\s*[TPFRCG]\d+)*\]")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[])")


def split_claims(answer: str) -> List[str]:
    claims = []
    for sentence in SENT_SPLIT.split(answer or ""):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 40:
            continue
        if sentence.startswith(("#", "-", "*", "|")):
            continue
        claims.append(sentence)
    return claims


class SemanticGrounder:
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.environ.get(
            "SCIPAL_GROUNDING_MODEL", RERANK_MODEL
        )
        self._model = None

    def _ensure(self) -> bool:
        if self._model is not None:
            return True
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            return True
        except Exception:  # noqa: BLE001
            return False

    def check(
        self,
        answer: str,
        evidence_texts: Iterable[str],
        min_support: float = 0.2,
        min_ratio: float = 0.5,
    ) -> Dict:
        claims = split_claims(answer)
        if not claims:
            return {"grounded": True, "supported_ratio": 1.0, "claims": 0, "unsupported": []}
        if not self._ensure():
            return {"grounded": True, "supported_ratio": 1.0, "claims": len(claims), "unsupported": [], "error": "model unavailable"}
        contexts = [text for text in evidence_texts if text and len(text) > 20]
        if not contexts:
            return {"grounded": False, "supported_ratio": 0.0, "claims": len(claims), "unsupported": claims[:5]}
        supported = 0
        unsupported = []
        for claim in claims:
            pairs = [(claim, context) for context in contexts]
            try:
                scores = self._model.predict(pairs, show_progress_bar=False)
            except Exception:  # noqa: BLE001
                unsupported.append(claim)
                continue
            if max(float(score) for score in scores) >= min_support:
                supported += 1
            else:
                unsupported.append(claim)
        ratio = supported / len(claims)
        return {
            "grounded": ratio >= min_ratio,
            "supported_ratio": round(ratio, 4),
            "claims": len(claims),
            "supported": supported,
            "unsupported": unsupported[:5],
        }


_GROUNDER = None


def get_semantic_grounder() -> SemanticGrounder:
    global _GROUNDER
    if _GROUNDER is None:
        _GROUNDER = SemanticGrounder()
    return _GROUNDER
