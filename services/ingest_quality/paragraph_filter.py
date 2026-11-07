"""Backend-only paragraph indexability gate.

This is not client tracking. It decides whether a parsed paragraph belongs in
the vector index before embeddings are generated.
"""

from __future__ import annotations

import re

_SECTION_SKIP = {
    "references",
    "reference",
    "acknowledgements",
    "acknowledgments",
    "funding",
    "conflict of interest",
    "conflicts of interest",
    "author contributions",
    "keywords",
    "abbreviations",
}

_LABEL_RE = re.compile(
    r"^(figure|fig\.?|table|scheme|supplementary|appendix)\s*\d+[a-z]?[.:]?\s*$",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"^\d+(\.\d+)*[.)、]?$")
_SECTION_NUMBER_RE = re.compile(r"^\d+(\.\d+)*\s+\S")
_URL_RE = re.compile(r"^(https?://|doi:|www\.)", re.IGNORECASE)
_AFFILIATION_RE = re.compile(
    r"^(department|division|university|hospital|institute|school|college|center|centre|faculty)\b",
    re.IGNORECASE,
)
_BOILERPLATE_RE = re.compile(
    r"^(financiamento|funding|conflict|acknowledg|correspondence|keywords|abbreviations)\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def index_skip_reason(text: str, section_l1: str = "", section_l2: str = "") -> str:
    t = _normalize(text)
    section = _normalize(section_l1).lower()
    if not t:
        return "empty"
    if section in _SECTION_SKIP:
        return "reference_section"
    if len(t) < 10:
        return "too_short"
    if _NUMBER_RE.fullmatch(t) or _LABEL_RE.fullmatch(t):
        return "label_only"
    if _URL_RE.match(t) and len(t) < 120:
        return "url_only"
    if _BOILERPLATE_RE.match(t) and len(t) < 120:
        return "boilerplate"
    if _AFFILIATION_RE.match(t) and len(t) < 120:
        return "affiliation"
    letters = sum(ch.isalpha() for ch in t)
    if letters == 0:
        return "no_letters"
    if len(t) < 80 and re.search(r"[,;]", t) and not re.search(r"[.!?。！？]$", t):
        # author lists / affiliation fragments, not sentences
        if sum(ch.isupper() for ch in t) >= 2:
            return "author_or_fragment"
    if len(t) < 60 and _SECTION_NUMBER_RE.match(t):
        return "section_heading"
    if len(t) < 60 and t.isupper():
        return "all_caps_heading"
    if len(t) < 60 and not re.search(r"[.!?。！？:：]$", t):
        words = t.split()
        if len(words) >= 2 and all(w[:1].isupper() for w in words if w):
            return "title_like_heading"
    if len(t) < 80 and sum(ch.isdigit() for ch in t) / max(len(t), 1) > 0.5:
        return "numeric_dominant"
    return ""
