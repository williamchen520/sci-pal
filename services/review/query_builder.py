"""Section query construction for retrieval.

The old behaviour joined the first five keywords verbatim, which let generic
terms ("inflammation", "signaling") dilute specific ones ("TLR4", "sepsis") and
pulled retrieval toward generic review articles. This module keeps the specific
terms first and caps the query at a few words.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

#: Words that carry almost no discriminative power in this corpus.
GENERIC_TERMS = frozenset(
    {
        "inflammation",
        "inflammatory",
        "immune",
        "immunity",
        "disease",
        "diseases",
        "disorder",
        "disorders",
        "review",
        "mechanism",
        "mechanisms",
        "signaling",
        "signalling",
        "signal",
        "signals",
        "pathway",
        "pathways",
        "response",
        "responses",
        "role",
        "roles",
        "effect",
        "effects",
        "study",
        "studies",
        "patient",
        "patients",
        "human",
        "humans",
        "cell",
        "cells",
        "introduction",
        "background",
        "methods",
        "methodology",
        "results",
        "discussion",
        "conclusion",
        "treatment",
        "therapeutic",
        "potential",
        "analysis",
        "clinical",
        "molecular",
    }
)

DEFAULT_MAX_TERMS = 3


def build_section_query(
    keywords: Sequence[str],
    *,
    title: str = "",
    max_terms: int = DEFAULT_MAX_TERMS,
) -> str:
    """Build a short, specific retrieval query for one section.

    Order is preserved; generic-only terms are dropped when at least one
    specific term exists; the result is capped at ``max_terms``.
    """
    ordered = _unique(keywords)
    specific = [term for term in ordered if _is_specific(term)]
    chosen = (specific or ordered)[:max_terms]
    if not chosen:
        chosen = _unique(re.split(r"[\s/]+", title))[:max_terms]
    return " ".join(chosen)


def _is_specific(term: str) -> bool:
    words = [word for word in re.split(r"[\s\-_/]+", term.lower()) if word]
    return bool(words) and not all(word in GENERIC_TERMS for word in words)


def _unique(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            ordered.append(text)
    return ordered
