"""
Build Citation-Paragraph Bidirectional Index
V20.3 - Match in-text citations (numbered + author-year) against reference list.

For each paper:
  1. Load all citations (reference list) from Grobid
  2. Scan paragraphs for in-text citation markers
  3. Match against reference list
  4. Insert into paper_index (paragraph -> citation)
"""
import sqlite3
import re
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"

# --- Regex patterns ---

# Numbered: [1], [2], [1-3], [1, 2, 3], [1-3, 5]
NUMBERED_RE = re.compile(r'\[(\d+(?:[\-,\s]+\d+)*)\]')

# Author-year: (Smith, 2020), (J. Smith et al., 2020), (Smith and Jones, 2020)
# Also: Smith (2020), Smith et al. (2020)
AUTHOR_YEAR_PAREN_RE = re.compile(
    r'\(([A-Z][A-Za-z\'\-]+(?:,?\s+[A-Z]\.?)?(?:\s+et al\.)?(?:\s+and\s+[A-Z][A-Za-z\'\-]+)?,?\s*\d{4}[a-z]?)'
)

# Author-year outside parens: Smith (2020), Smith et al. (2020)
AUTHOR_YEAR_PLAIN_RE = re.compile(
    r'([A-Z][A-Za-z\'\-]+(?:\s+et al\.)?)\s*\((\d{4}[a-z]?)\)'
)


def normalize_name(name: str) -> str:
    """Normalize author name for matching: lowercase, strip punctuation."""
    return re.sub(r'[^a-z]', '', name.lower())


def parse_numbered_refs(group: str) -> list[int]:
    """Parse '1-3, 5' into [1, 2, 3, 5]."""
    result = []
    parts = re.split(r'[,;]', group)
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                a, b = part.split('-')
                result.extend(range(int(a), int(b) + 1))
            except:
                pass
        else:
            try:
                result.append(int(part))
            except:
                pass
    return result


def build_ref_index(citations: list[dict]) -> dict:
    """Build lookup index for citations.
    Returns: {key: citation_id}
    where key is (surname_lower, initial_lower_or_empty, year)
    """
    index = {}
    for cit in citations:
        if not cit['authors'] or not cit['year']:
            continue
        # Get first author
        first_author = cit['authors'].split(';')[0].strip()
        # Parse "Smith, John" or "John Smith" or "Smith J"
        parts = re.split(r'[,\s]+', first_author)
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            # Could be "Smith, John" or "John Smith"
            if ',' in first_author:
                surname = parts[0]
                initial = parts[1][0] if len(parts) > 1 and parts[1] else ''
            else:
                # "John Smith" or "Smith J"
                surname = parts[-1]
                initial = parts[0][0] if parts[0] else ''
        else:
            surname = parts[0] if parts else ''
            initial = ''

        surname_norm = normalize_name(surname)
        initial_norm = normalize_name(initial)
        year = str(cit['year'])

        # Key without initial (for (Smith, 2020) case)
        key_no_initial = (surname_norm, '', year)
        if key_no_initial not in index:
            index[key_no_initial] = cit['citation_id']

        # Key with initial (for (J. Smith, 2020) case)
        if initial_norm:
            key_with_initial = (surname_norm, initial_norm, year)
            if key_with_initial not in index:
                index[key_with_initial] = cit['citation_id']

    return index


def match_author_year(text: str, ref_index: dict) -> list[str]:
    """Try to match an author-year citation string against reference index."""
    # Extract surname and year
    m = re.match(
        r'([A-Z][A-Za-z\'\-]+)(?:,?\s+([A-Z])\.?)?(?:\s+et al\.)?.*?(\d{4}[a-z]?)',
        text
    )
    if not m:
        return []

    surname, initial, year = m.groups()
    surname_norm = normalize_name(surname)
    initial_norm = normalize_name(initial or '')

    # Try with initial first
    if initial_norm:
        key = (surname_norm, initial_norm, year)
        if key in ref_index:
            return [ref_index[key]]

    # Try without initial
    key = (surname_norm, '', year)
    if key in ref_index:
        return [ref_index[key]]

    return []


def build_citation_index():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Get all papers
    cur.execute("SELECT paper_id FROM papers")
    papers = [row[0] for row in cur.fetchall()]

    total_links = 0
    papers_processed = 0

    for paper_id in papers:
        # Get all citations for this paper
        cur.execute("""
            SELECT citation_id, authors, title, year, ref_number
            FROM citations WHERE paper_id = ?
        """, (paper_id,))
        cit_rows = cur.fetchall()
        citations = []
        cit_by_num = {}
        for citation_id, authors, title, year, ref_number in cit_rows:
            cit = {'citation_id': citation_id, 'authors': authors, 'title': title, 'year': year, 'ref_number': ref_number}
            citations.append(cit)
            try:
                cit_by_num[int(ref_number)] = citation_id
            except:
                pass

        if not citations:
            continue

        ref_index = build_ref_index(citations)

        # Get all paragraphs for this paper
        cur.execute("""
            SELECT para_id, text FROM paragraphs WHERE paper_id = ?
        """, (paper_id,))
        paras = cur.fetchall()

        links = []
        for para_id, text in paras:
            if not text:
                continue

            # 1. Numbered citations: [1], [1-3]
            for m in NUMBERED_RE.finditer(text):
                refs = parse_numbered_refs(m.group(1))
                for r in refs:
                    if r in cit_by_num:
                        links.append((para_id, "paragraph", cit_by_num[r], "citation", "cites"))

            # 2. Author-year in parens: (Smith, 2020)
            for m in AUTHOR_YEAR_PAREN_RE.finditer(text):
                candidate = m.group(1)
                matched = match_author_year(candidate, ref_index)
                for cit_id in matched:
                    links.append((para_id, "paragraph", cit_id, "citation", "cites"))

            # 3. Author-year plain: Smith (2020)
            for m in AUTHOR_YEAR_PLAIN_RE.finditer(text):
                candidate = f"{m.group(1)}, {m.group(2)}"
                matched = match_author_year(candidate, ref_index)
                for cit_id in matched:
                    links.append((para_id, "paragraph", cit_id, "citation", "cites"))

        # Insert into paper_index
        for src_id, src_type, tgt_id, tgt_type, rel in links:
            idx_id = f"idx_{paper_id[:15]}_{src_id[-10:]}_{tgt_id[-10:]}"
            cur.execute("""
                INSERT OR IGNORE INTO paper_index
                (index_id, paper_id, source_id, source_type, target_id, target_type, relation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (idx_id, paper_id, src_id, src_type, tgt_id, tgt_type, rel))

        total_links += len(links)
        papers_processed += 1
        if papers_processed % 10 == 0:
            print(f"  [{papers_processed}/{len(papers)}] processed, {total_links} links so far")

    conn.commit()

    # Stats
    cur.execute("SELECT COUNT(*) FROM paper_index WHERE relation='cites'")
    total_cite_links = cur.fetchone()[0]

    print(f"\n✅ Done!")
    print(f"  Papers processed: {papers_processed}")
    print(f"  Total citation links: {total_cite_links}")

    conn.close()


if __name__ == "__main__":
    build_citation_index()
