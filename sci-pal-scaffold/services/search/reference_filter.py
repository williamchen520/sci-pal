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

Audit (read-only, prints what WOULD be excluded):
  python -m services.search.reference_filter
"""
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

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


def _audit():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT para_id, paper_id, section_level1, section_level2, text
           FROM paragraphs"""
    ).fetchall()

    flagged = []
    section_hits = 0
    for r in rows:
        if is_reference_entry(r["text"], r["section_level1"], r["section_level2"]):
            flagged.append(r)
            if _section_is_references(r["section_level1"]) or \
               _section_is_references(r["section_level2"]):
                section_hits += 1

    print("=" * 64)
    print("🔎 Reference-entry audit (read-only, nothing changed)")
    print("=" * 64)
    print(f"Total paragraphs : {len(rows)}")
    print(f"Flagged as refs  : {len(flagged)} "
          f"({100*len(flagged)/max(1,len(rows)):.1f}%)")
    print(f"  under a References-labelled section: {section_hits}")
    print(f"  caught by content pattern only     : "
          f"{len(flagged) - section_hits}")
    print("\nSample flagged (first 15):")
    for r in flagged[:15]:
        preview = _normalize(r["text"])[:95]
        sec = r["section_level1"] or ""
        print(f"  • [{sec[:28]:28}] {preview}")

    # Precision check: show short flagged items (most likely false positives)
    short = [r for r in flagged if len(_normalize(r["text"])) < 60]
    if short:
        print(f"\n⚠️  {len(short)} flagged items are <60 chars — eyeball these "
              f"for false positives:")
        for r in short[:15]:
            print(f"  ? {_normalize(r['text'])[:90]}")


if __name__ == "__main__":
    _audit()
