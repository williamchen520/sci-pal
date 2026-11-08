"""
High-precision reference-entry filter.
V21.7 - Keep bibliography entries out of QA paragraph retrieval.

Reference-list items (e.g. "10. Bancerek, J. et al. ... Immunity 38,
250-262 (2013).") get stored as normal paragraphs and pollute semantic/QA
search. They already live, properly structured, in the `citations` table
(via Grobid), so dropping them from paragraph QA loses nothing.

Docling often fails to label the "References" heading (the entries inherit
the paper title as their section), so section name alone is unreliable.
This detector therefore relies primarily on high-precision *content*
patterns and uses the section name only as a secondary signal.

"""
import re


REFERENCE_SECTION_TERMS = (
    "references", "reference", "bibliography", "literature cited",
    "works cited", "reference list",
)

# 19xx/20xx year, page ranges, DOI / volume cues.
_YEAR = r"(?:19|20)\d{2}"
_PAGE_RANGE = r"\d{1,4}\s*[-–:]\s*\d{1,4}"
_DOI = r"doi\.?\s*:?\s*10\."


def _normalize(text: str) -> str:
    """Collapse PDF spacing artifacts, e.g. '- 10 . Bancerek , J .'."""
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"\s+([.,;:)])", r"\1", t)
    return t


def _section_is_references(section: str) -> bool:
    if not section:
        return False
    s = _normalize(section).lower()
    return any(term in s for term in REFERENCE_SECTION_TERMS)


def _looks_bibliographic(t: str) -> bool:
    """Year plus a page range / DOI / volume-page cue typical of a citation."""
    if not re.search(_YEAR, t):
        return False
    return bool(re.search(_PAGE_RANGE, t) or "doi" in t.lower()
                or re.search(r"\bvol\.?\s*\d", t, re.I))


def is_reference_entry(text: str, section_l1: str = None,
                       section_l2: str = None) -> bool:
    """
    True if a paragraph is a bibliography entry rather than body text.
    High precision: content must show a numbered author lead, or sit under a
    References heading AND carry bibliographic cues.
    """
    if not text:
        return False
    t = _normalize(text)
    in_ref_section = (_section_is_references(section_l1)
                      or _section_is_references(section_l2))

    lead = r"[-–—•*]?\s*\d{1,4}\s*[.)]\s+"
    # 1) "10. Bancerek, J." / "62. Cheon, H. & Stark, G. R."
    comma_initials = lead + r"[A-Z][A-Za-z'’\-]+,\s*[A-Z][A-Za-z]?\."
    if re.match(comma_initials, t):
        return True

    # 2) Vancouver style "10. Bancerek J, ... (2013)" (no comma before initials)
    vancouver = lead + r"[A-Z][a-z]+\s+[A-Z]{1,3}\b"
    if re.match(vancouver, t) and re.search(_YEAR, t):
        return True

    # 3) Under an explicit References heading and clearly bibliographic.
    if in_ref_section and _looks_bibliographic(t):
        return True

    return False
