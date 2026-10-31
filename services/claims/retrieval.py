"""Opposition-aware candidate retrieval for claim interrogation.

FTS is only the first-stage recall. The scorer adds qualifier coverage and
direction cues so that "same topic" sentences do not automatically look like
counter-evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "has", "have", "had", "not", "but", "into", "than", "using", "study",
    "patients", "patient", "results", "conclusion", "compared", "between",
    "their", "these", "those", "with", "without", "after", "before", "may",
    "can", "could", "should", "would", "also", "more", "less", "than", "among",
}
REFUTE_CUES = (
    "no significant", "not significant", "did not", "failed to", "no benefit",
    "no improvement", "not associated", "no association", "worse", "inferior",
    "shorter", "resistance", "resistant", "lack of", "contrary", "however",
    "no difference", "not superior", "decreased", "reduced benefit",
)
SUPPORT_CUES = (
    "improved", "superior", "significant", "benefit", "prolonged",
    "associated with", "increased survival", "better", "effective",
)
BOUNDARY_CUES = (
    "subgroup", "elderly", "dose", "high-dose", "low-dose", "resistance",
    "limitation", "only in", "selected", "pretreated", "first-line",
    "second-line", "safety", "adverse",
)


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for token in TOKEN_RE.findall(text or ""):
        low = token.lower()
        if len(low) < 2 or low in STOP or low in out:
            continue
        out.append(low)
    return out


def _qualifier_values(qualifiers: Dict[str, Any] | None) -> List[str]:
    if not isinstance(qualifiers, dict):
        return []
    values = []
    for value in qualifiers.values():
        if isinstance(value, (list, tuple)):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def _phrase(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\-\s]", " ", str(value or ""))
    tokens = [
        token.lower()
        for token in cleaned.split()
        if len(token) >= 2 and token.lower() not in STOP
    ]
    if not tokens:
        return ""
    if len(tokens) > 4:
        tokens = tokens[:4]
    return " ".join(tokens)


def _qualifier_phrases(qualifiers: Dict[str, Any] | None) -> List[str]:
    if not isinstance(qualifiers, dict):
        return []
    phrases: List[str] = []
    for key, value in qualifiers.items():
        if key in {"unit", "time", "scope"} and not value:
            continue
        values = value if isinstance(value, (list, tuple)) else [value]
        for item in values:
            for part in re.split(r"[+,/;]", str(item or "")):
                phrase = _phrase(part)
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
    return phrases


def build_queries(claim_text: str, qualifiers: Dict[str, Any] | None = None) -> Dict[str, str]:
    qualifier_phrases = _qualifier_phrases(qualifiers)
    claim_terms = [token for token in _tokens(claim_text) if len(token) >= 4]
    phrases = list(dict.fromkeys(qualifier_phrases + claim_terms))[:10]
    base = " OR ".join(f'"{phrase}"' for phrase in phrases)
    if not base:
        return {"support": "", "refute": "", "boundary": ""}
    refute_cues = " OR ".join(f'"{cue}"' for cue in REFUTE_CUES)
    boundary_cues = " OR ".join(f'"{cue}"' for cue in BOUNDARY_CUES)
    return {
        "support": base,
        "refute": f"({base}) AND ({refute_cues})",
        "boundary": f"({base}) AND ({boundary_cues})",
    }


def _overlap(tokens: Iterable[str], text: str) -> float:
    wanted: Set[str] = {token for token in tokens if token}
    if not wanted:
        return 0.0
    found = set(_tokens(text))
    return len(wanted & found) / len(wanted)


def _cue_hits(text: str, cues: Iterable[str]) -> int:
    lowered = (text or "").lower()
    return sum(1 for cue in cues if cue in lowered)


def rank_candidates(
    claim_text: str,
    qualifiers: Dict[str, Any] | None,
    rows: List[Dict[str, Any]],
    direction: str = "support",
) -> List[Dict[str, Any]]:
    qualifier_tokens = _tokens(" ".join(_qualifier_values(qualifiers)))
    claim_tokens = _tokens(claim_text)
    cues = REFUTE_CUES if direction == "oppose" else SUPPORT_CUES
    ranked = []
    for row in rows:
        quote = row.get("quote") or ""
        base = _overlap(claim_tokens + qualifier_tokens, quote)
        qualifier = _overlap(qualifier_tokens, quote)
        cue = min(_cue_hits(quote, cues) / 2.0, 1.0)
        score = 0.50 * base + 0.30 * qualifier + 0.20 * cue
        enriched = dict(row)
        enriched.update(
            {
                "score": round(score, 4),
                "qualifier_score": round(qualifier, 4),
                "direction_cues": _cue_hits(quote, cues),
            }
        )
        ranked.append(enriched)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked
