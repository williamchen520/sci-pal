"""Section query construction for retrieval.

The old behaviour joined the first five keywords verbatim, which let generic
terms ("inflammation", "signaling") dilute specific ones ("TLR4", "sepsis") and
pulled retrieval toward generic review articles. This module keeps the specific
terms first and caps the query at a few words.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

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


def count_term_hits(text: str, terms: Sequence[str]) -> int:
    """How many distinct query terms appear in ``text`` (case-insensitive)."""
    haystack = str(text or "").lower()
    return sum(1 for term in terms if term and term.lower() in haystack)


def is_paper_relevant(
    text: str,
    terms: Sequence[str],
    *,
    title: str | None = None,
    min_hits: int | None = None,
) -> bool:
    """Judge whether a paper is on-topic.

    With ``title`` provided, the paper must mention at least one query term in
    its title (text-body mentions alone are too weak: generic reviews often
    name-drop the topic in passing).
    """
    if not terms:
        return True
    if title is not None and count_term_hits(title, terms) == 0:
        return False
    required = min_hits if min_hits is not None else (1 if len(terms) <= 1 else 2)
    return count_term_hits(f"{title or ''} {text}", terms) >= required


def rank_papers(
    paper_ids: Sequence[str],
    titles: Mapping[str, str],
    terms: Sequence[str],
    scores: Mapping[str, float] | None = None,
) -> list[str]:
    """Order papers by title-term hits, then by their best paragraph score.

    Hard filters on titles cut recall too aggressively (an earlier attempt left
    only 3 evidence cards); ordering keeps every candidate and only decides
    which papers survive the per-section cap.
    """
    scores = scores or {}

    def key(index: int) -> tuple[int, float, int]:
        paper_id = paper_ids[index]
        hits = count_term_hits(titles.get(paper_id, ""), terms)
        return (-hits, -float(scores.get(paper_id, 0.0)), index)

    return [paper_ids[index] for index in sorted(range(len(paper_ids)), key=key)]
