"""
Line-level front-matter / boilerplate cleaner for retrieved paragraphs.
V21.8 - Remove journal header, author affiliations, copyright, DOI links,
        editor info, etc. that Docling often merges into the first body
        paragraph of a paper.

Unlike reference_filter (which drops whole paragraphs), this works LINE BY
LINE: boilerplate rows are stripped, real body rows are kept. This matters
because the first paragraph of many papers looks like:

    Edited by Helen C Su and Jean-Laurent Casanova
    Available online 8th April 2021
    https://doi.org/10.1016/j.coi.2021.02.009
    0952-7915/ © 2021 Elsevier Ltd. All rights reserved.
    Signal transducer and activator of transcription 1 (STAT1) is ...

Dropping the whole paragraph would lose the real body text; line-level
cleaning keeps only the last line.

Usage (audit, read-only):
  python -m services.search.boilerplate_filter
"""
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "research.db"

# Each pattern is matched against a stripped, single line.
# High precision only — if in doubt, keep the line.
BOILERPLATE_LINE_PATTERNS = [
    # --- Editor / journal metadata ---
    r"^Edited by\b",
    r"^For a complete overview",
    r"^Available online\b",
    r"^Academic Editor\s*:",
    r"^Guest Editor(s)?\s*:",
    r"^Editor(s)?\s*:",
    r"^Handling Editor\s*:",

    # --- Links / identifiers on their own line ---
    r"^https?://(dx\.)?doi\.org/",
    r"^mailto:",
    r"^\[?https?://doi\.org/",          # markdown-wrapped DOI link

    # --- Copyright / ISSN ---
    r"^[©©ã]\s*\d{4}",                   # © 2021 / ã 2021 (PDF encoding glitch)
    r"^Copyright\b",
    r"All rights reserved\.?$",
    r"^\d{4}-\d{3}[\dXx]/?",            # ISSN e.g. 0952-7915/
    r"^ISSN\s*:",

    # --- Author affiliations (numbered + institution keyword, allowing
    #     leading place/adjective words and lowercase function words) ---
    r"^\d+\s+(([A-Z][A-Za-z'’\-]+|of|for|and|the|in|at|on|to|with)\s+){0,6}"
    r"(Department|Institute|University|College|Laboratory|Lab|Center|"
    r"Centre|School|Faculty|Division|Unit|Program|Hospital|Clinic|"
    r"Foundation|Academy)\b",

    # --- Author name + email on one line (e.g. "Xiaodong Zhao mailto:...") ---
    r"^[A-Z][A-Za-z'’\-]+(\s+[A-Z][A-Za-z'’\-]+){0,3}\s+mailto:",
    # --- Author name + bare email at end of line (e.g. "Xiaodong Zhao zx@aliyun.com") ---
    r"^[A-Z][A-Za-z'’\-]+(\s+[A-Z][A-Za-z'’\-]+){1,3}\s+[\w.+-]+@[\w.-]+\.\w+\s*$",

    # --- Submission dates ---
    r"^(Received|Accepted|Revised|Published online|Published)\s+\w",

    # --- Corresponding author ---
    r"^\*?\s*Correspond(ence|ing)\b",
    r"^\*?\s*Corresponding author\b",

    # --- Journal boilerplate ---
    r"^Contents lists available at",
    r"^ScienceDirect$",
    r"^www\.[a-z0-9.-]+\.[a-z]{2,}/?",
    r"^journal homepage",
    r"^Journal homepage",

    # --- Bare heading lines that Docling failed to tag as headings ---
    r"^Abstract$",
    r"^Introduction$",
    r"^Keywords?\s*:$",                  # bare "Keywords:" with no content
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_LINE_PATTERNS]


def is_boilerplate_line(line: str) -> bool:
    """True if a single (stripped) line is front-matter noise."""
    if not line:
        return False
    s = line.strip()
    if not s:
        return True
    # Strip an optional leading bullet marker (*, -, •, –, —) so that
    # "- 2 Chongqing Key Laboratory..." and "* Xiaodong Zhao email@..."
    # are tested the same as unbulleted lines.
    s = re.sub(r"^[*\-–—•]\s+", "", s)
    return any(p.search(s) for p in _COMPILED)


def clean_boilerplate(text: str) -> str:
    """
    Remove boilerplate lines from a paragraph. Returns the cleaned text.
    If everything was boilerplate, returns "" (caller should skip the hit).
    """
    if not text:
        return ""
    kept = []
    for line in text.splitlines():
        if is_boilerplate_line(line):
            continue
        kept.append(line)
    # Collapse runs of blank lines that boilerplate removal may leave.
    result = "\n".join(kept).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def _audit():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT para_id, paper_id, text FROM paragraphs"
    ).fetchall()

    changed = 0
    total_removed_lines = 0
    samples = []

    for r in rows:
        original = r["text"] or ""
        cleaned = clean_boilerplate(original)
        if cleaned != original:
            changed += 1
            removed = max(0, len(original.splitlines()) - len(cleaned.splitlines()))
            total_removed_lines += removed
            if len(samples) < 12:
                # Show the first 3 removed lines for context.
                removed_lines = [
                    ln.strip() for ln in original.splitlines()
                    if is_boilerplate_line(ln)
                ][:3]
                samples.append((r["para_id"], removed_lines, len(cleaned)))

    print("=" * 64)
    print("🧹 Boilerplate line-cleaner audit (read-only)")
    print("=" * 64)
    print(f"Total paragraphs     : {len(rows)}")
    print(f"Paragraphs affected  : {changed} "
          f"({100*changed/max(1,len(rows)):.1f}%)")
    print(f"Total lines removed  : {total_removed_lines}")
    print("\nSample removed lines (first 3 per paragraph):")
    for pid, lines, remaining in samples:
        print(f"  • {pid}  (→ {remaining} chars kept)")
        for ln in lines:
            print(f"      − {ln[:80]}")


if __name__ == "__main__":
    _audit()
