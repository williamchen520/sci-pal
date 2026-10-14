"""
Post-processing: Find missing DOIs by searching through paragraph text
- Paper's own DOI: only search BEFORE references section
- Citation DOIs: search references section and update citations table
"""
import sqlite3
import re
from pathlib import Path

project_root = Path(__file__).parent.parent
db_path = project_root / "data" / "research.db"


def clean_doi(raw: str) -> str:
    """Clean up a DOI string that might have spaces or line breaks"""
    cleaned = re.sub(r'\s+', '', raw)
    return cleaned.rstrip('.,;)')


def extract_doi_from_text(text: str) -> str:
    """Extract DOI from text, handling spaces in URLs"""
    if not text:
        return None
    
    # First try standard patterns
    patterns = [
        r'https?://doi\.org/(10\.\d{4,}/[A-Za-z0-9\-._()]+)',
        r'https?://dx\.doi\.org/(10\.\d{4,}/[A-Za-z0-9\-._()]+)',
        r'doi:\s*(10\.\d{4,}/[A-Za-z0-9\-._()]+)',
        r'(?<![\w.])(10\.\d{4,}/[A-Za-z0-9\-._()]+)',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return clean_doi(m.group(1))
    
    # Try handling spaced DOI: remove spaces and try again
    no_spaces = re.sub(r'\s+', '', text)
    for pattern in patterns:
        m = re.search(pattern, no_spaces, re.IGNORECASE)
        if m:
            return clean_doi(m.group(1))
    
    return None


def find_references_bounds(cur, paper_id: str) -> tuple:
    """Find the start and end sequence numbers of the references section.
    
    Returns: (start_seq, end_seq)
    - Paper's own content is BEFORE start_seq AND AFTER end_seq
    - References content is BETWEEN start_seq and end_seq
    """
    cur.execute("""
        SELECT sequence, section_level1, text 
        FROM paragraphs 
        WHERE paper_id = ? 
        ORDER BY sequence
    """, (paper_id,))
    paragraphs = cur.fetchall()
    
    if not paragraphs:
        return (999999, 0)
    
    ref_keywords = ['references', 'bibliography', 'works cited', 'literature cited']
    start_seq = None
    end_seq = len(paragraphs)
    
    # Find start: look for references section heading
    for seq, section, text in paragraphs:
        is_ref_heading = False
        if section:
            section_lower = section.lower().strip()
            for kw in ref_keywords:
                if kw in section_lower:
                    is_ref_heading = True
                    break
        if not is_ref_heading and text and len(text) < 100:
            text_lower = text.lower().strip()
            for kw in ref_keywords:
                if text_lower == kw or text_lower.startswith(kw + '.'):
                    is_ref_heading = True
                    break
        if is_ref_heading:
            start_seq = seq
            break
    
    if start_seq is None:
        # If not found, assume references start at 80%
        start_seq = int(len(paragraphs) * 0.8)
        return (start_seq, len(paragraphs))
    
    # Find end: look for what comes AFTER references
    # Common post-references sections: acknowledgments, supplementary, data availability, 
    # author contributions, conflict of interest, funding, figure legends, tables
    post_ref_keywords = [
        'acknowledg', 'supplementary', 'supplemental',
        'data availability', 'author contribution', 'author\'s contribution',
        'conflict of interest', 'competing interest', 'funding',
        'figure legend', 'table legend', 'appendix',
        'declaration', 'ethic', 'consent',
        'open access', 'license', 'copyright',
        'cited by', 'altmetric', 'metrics',
    ]
    
    for seq, section, text in paragraphs[start_seq:]:
        is_post_ref = False
        if section:
            section_lower = section.lower().strip()
            for kw in post_ref_keywords:
                if kw in section_lower:
                    is_post_ref = True
                    break
        if not is_post_ref and text and len(text) < 100:
            text_lower = text.lower().strip()
            for kw in post_ref_keywords:
                if text_lower == kw or text_lower.startswith(kw):
                    is_post_ref = True
                    break
        if is_post_ref:
            end_seq = seq
            break
    
    return (start_seq, end_seq)


def main():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # ============================================================
    # Part 1: Fix paper's own DOIs (search BEFORE references)
    # ============================================================
    print("=" * 60)
    print("🔧 Part 1: Fix paper's own DOIs")
    print("=" * 60)
    
    cur.execute("SELECT paper_id, filename, title FROM papers WHERE doi IS NULL OR doi = ''")
    missing_doi = cur.fetchall()
    
    print(f"Found {len(missing_doi)} papers with missing DOI\n")
    
    updated_papers = 0
    still_missing = []
    
    for paper_id, filename, title in missing_doi:
        print(f"📄 {filename[:50]}...")
        
        # Find where references start and end
        ref_start, ref_end = find_references_bounds(cur, paper_id)
        print(f"   References: #{ref_start} → #{ref_end}")
        
        # Get paragraphs BEFORE references (main text)
        cur.execute("""
            SELECT sequence, text FROM paragraphs 
            WHERE paper_id = ? AND sequence < ?
            ORDER BY sequence
        """, (paper_id, ref_start))
        main_paragraphs = cur.fetchall()
        
        # Get paragraphs AFTER references (supplementary notes, appendices, etc.)
        cur.execute("""
            SELECT sequence, text FROM paragraphs 
            WHERE paper_id = ? AND sequence >= ?
            ORDER BY sequence
        """, (paper_id, ref_end))
        after_ref_paragraphs = cur.fetchall()
        
        found_doi = None
        found_loc = None
        
        # Search 1: before references (main text)
        search_limit = int(len(main_paragraphs) * 0.9)
        for seq, text in main_paragraphs[:search_limit]:
            doi = extract_doi_from_text(text)
            if doi:
                found_doi = doi
                found_loc = f"para #{seq} (before refs)"
                break
        
        # Search 2: after references (supplementary notes, etc.)
        if not found_doi and after_ref_paragraphs:
            for seq, text in after_ref_paragraphs[:20]:  # only first 20 after refs
                doi = extract_doi_from_text(text)
                if doi:
                    found_doi = doi
                    found_loc = f"para #{seq} (after refs)"
                    break
        
        if found_doi:
            cur.execute("UPDATE papers SET doi = ? WHERE paper_id = ?", (found_doi, paper_id))
            conn.commit()
            print(f"   ✅ Found: {found_doi} (at {found_loc})")
            updated_papers += 1
        else:
            print(f"   ❌ Not found")
            still_missing.append((filename, title))
    
    print(f"\n📊 Part 1 Result:")
    print(f"   Updated: {updated_papers}")
    print(f"   Still missing: {len(still_missing)}")
    if still_missing:
        for fn, t in still_missing:
            print(f"     - {fn[:50]}")
    
    # ============================================================
    # Part 2: Fix citation DOIs (from references section)
    # ============================================================
    print("\n" + "=" * 60)
    print("🔧 Part 2: Fix citation DOIs from references section")
    print("=" * 60)
    
    # Get all citations without DOI
    cur.execute("SELECT citation_id, paper_id, raw_text FROM citations WHERE doi IS NULL OR doi = ''")
    missing_cite_doi = cur.fetchall()
    
    print(f"Found {len(missing_cite_doi)} citations with missing DOI\n")
    
    updated_cites = 0
    for citation_id, paper_id, raw_text in missing_cite_doi:
        if not raw_text:
            continue
        
        doi = extract_doi_from_text(raw_text)
        if doi:
            cur.execute("UPDATE citations SET doi = ? WHERE citation_id = ?", (doi, citation_id))
            updated_cites += 1
    
    conn.commit()
    print(f"   ✅ Updated {updated_cites} citations with DOI")
    
    # Final stats
    cur.execute("SELECT COUNT(*) FROM papers WHERE doi IS NOT NULL AND doi != ''")
    papers_with_doi = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM citations WHERE doi IS NOT NULL AND doi != ''")
    cites_with_doi = cur.fetchone()[0]
    
    print("\n" + "=" * 60)
    print("📊 Final Stats:")
    print(f"   Papers with DOI: {papers_with_doi} / 46")
    print(f"   Citations with DOI: {cites_with_doi}")
    
    conn.close()


if __name__ == "__main__":
    main()
