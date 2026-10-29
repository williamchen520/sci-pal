"""Evidence-grounded answer checks.

This is a deterministic guard against parametric knowledge: a factual sentence
must (a) carry a citation and (b) share enough content with the evidence text.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List

CITE_RE = re.compile(r"\[[TPFRCG]\d+(?:\s*,\s*[TPFRCG]\d+)*\]")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "were", "has", "have", "what", "how", "does", "did", "into", "than",
    "based", "provided", "evidence", "according", "however", "therefore",
}
META = re.compile(
    r"^(based on|according to|the provided|the evidence|in summary|overall|"
    r"note that|importantly|references|sources)\b",
    re.I,
)


def _tokens(text: str) -> set:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if len(token) > 1 and token.lower() not in STOP
    }


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", text or "")
    return [part.strip() for part in parts if part.strip()]


def support_ratio(sentence: str, evidence_tokens: set) -> float:
    tokens = _tokens(CITE_RE.sub(" ", sentence))
    if not tokens:
        return 0.0
    return len(tokens & evidence_tokens) / len(tokens)


def check_grounding(
    answer: str,
    evidence_text: str,
    min_support: float = 0.5,
    min_supported_ratio: float = 0.5,
) -> Dict:
    evidence_tokens = _tokens(evidence_text)
    factual = []
    for sentence in split_sentences(answer):
        stripped = CITE_RE.sub("", sentence).strip()
        if len(_tokens(stripped)) < 4 or META.match(stripped) or stripped.startswith("#"):
            continue
        factual.append(sentence)
    supported = []
    unsupported = []
    for sentence in factual:
        cited = bool(CITE_RE.search(sentence))
        ratio = support_ratio(sentence, evidence_tokens)
        if cited and ratio >= min_support:
            supported.append(sentence)
        else:
            unsupported.append(sentence)
    ratio = len(supported) / len(factual) if factual else 1.0
    return {
        "grounded": ratio >= min_supported_ratio,
        "supported_ratio": round(ratio, 4),
        "factual_sentences": len(factual),
        "supported": len(supported),
        "unsupported": unsupported[:5],
    }
