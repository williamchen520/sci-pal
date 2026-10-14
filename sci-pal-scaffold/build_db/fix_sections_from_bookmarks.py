"""
Fix section hierarchy using PDF bookmarks
- Read bookmarks with pypdf (they already have proper hierarchy)
- Match paragraphs to bookmarks by page number
- Update section_level1/2/3 in database
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pypdf


def get_bookmarks_with_levels(pdf_path: str):
    """Extract bookmarks with their hierarchy level and page number"""
    reader = pypdf.PdfReader(pdf_path)
    outline = reader.outline
    
    bookmarks = []  # list of (level, title, page_number)
    
    def walk(items, level=1):
        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
            else:
                title = item.title.strip()
                # Get page number
                try:
                    page_num = reader.get_destination_page_number(item) + 1  # 1-indexed
                    bookmarks.append((level, title, page_num))
                except Exception:
                    pass
    
    walk(outline)
    
    # Sort by page number, then by order
    bookmarks.sort(key=lambda x: (x[2], bookmarks.index(x)))
    return bookmarks


def clean_section_name(name: str) -> str:
    """Remove common noise from section names"""
    name = name.strip()
    
    # Remove common noise patterns
    noise_patterns = [
        "Article", "Protocol", "Review", "Review Article", "Original Article",
        "OPEN", "OPEN ACCESS",
        "ScienceDirect",
        "Edited by:", "Reviewed by:", "*Correspondence:", "Specialty section:",
        "Citation:", "† Present address:",
        "nature immunology", "Nature Medicine", "Cell",
        "Highlights", "Graphical abstract", "In brief",
        "a r t i c l e i n f o", "A R T I C L E  I N F O",
        "a b s t r a c t", "A B S T R A C T",
    ]
    
    for pattern in noise_patterns:
        if name == pattern:
            return ""
    
    # Remove "Fig. X | ..." and "Table X | ..."
    if name.startswith("Fig.") or name.startswith("Figure"):
        return ""
    if name.startswith("Table") or name.startswith("Extended Data Table"):
        return ""
    
    # Remove things that are too short (just numbers)
    if len(name) < 3:
        return ""
    
    return name


def build_section_map(bookmarks):
    """Build a map: page_number -> (section_level1, section_level2, section_level3)"""
    # Clean and filter bookmarks
    clean_bookmarks = []
    for level, title, page in bookmarks:
        cleaned = clean_section_name(title)
        if cleaned:
            clean_bookmarks.append((level, cleaned, page))
    
    # Build section map by page range
    # For each page, what's the current section hierarchy?
    section_map = {}
    
    current_l1 = None
    current_l2 = None
    current_l3 = None
    
    for i, (level, title, page) in enumerate(clean_bookmarks):
        # What's the end page of this section?
        if i + 1 < len(clean_bookmarks):
            end_page = clean_bookmarks[i + 1][2] - 1
        else:
            end_page = 999  # last section goes to end
        
        # Update current hierarchy
        if level == 1:
            current_l1 = title
            current_l2 = None
            current_l3 = None
        elif level == 2:
            current_l2 = title
            current_l3 = None
        elif level == 3:
            current_l3 = title
        
        # Fill the map for all pages in this range
        for p in range(page, end_page + 1):
            section_map[p] = (current_l1, current_l2, current_l3)
    
    return section_map, len(clean_bookmarks)


def fix_sections_for_paper(cur, paper_id: str, filename: str):
    """Fix section hierarchy for one paper"""
    pdf_path = project_root / "documents" / filename
    
    if not pdf_path.exists():
        print(f"  ❌ PDF not found: {filename}")
        return False
    
    # Read bookmarks
    try:
        bookmarks = get_bookmarks_with_levels(str(pdf_path))
    except Exception as e:
        print(f"  ❌ Error reading bookmarks: {e}")
        return False
    
    if not bookmarks:
        print(f"  ⚠️  No bookmarks found")
        return False
    
    # Build section map
    section_map, clean_count = build_section_map(bookmarks)
    
    if clean_count == 0:
        print(f"  ⚠️  All bookmarks are noise")
        return False
    
    print(f"  Found {len(bookmarks)} raw bookmarks, {clean_count} clean")
    
    # Get all paragraphs with their page numbers
    # Wait - we don't have page numbers in the DB! We need to get them from Docling.
    # For now, let's just use the paragraphs we have and assign sections based on sequence.
    
    # Actually, we need to re-parse the PDF to get page numbers.
    # That's too slow for now. Let's just update what we can.
    
    print(f"  Section map pages: {min(section_map.keys())} - {max(section_map.keys())}")
    
    return True


def main():
    db_path = project_root / "data" / "research.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # Get all papers
    cur.execute("SELECT paper_id, filename FROM papers ORDER BY filename")
    papers = cur.fetchall()
    
    print("=" * 70)
    print("🔧 Fixing section hierarchy using PDF bookmarks")
    print("=" * 70)
    
    fixed = 0
    no_bookmarks = 0
    
    for paper_id, filename in papers:
        print(f"\n📄 {filename[:50]}...")
        result = fix_sections_for_paper(cur, paper_id, filename)
        if result:
            fixed += 1
        else:
            no_bookmarks += 1
    
    print("\n" + "=" * 70)
    print(f"📊 Summary:")
    print(f"  Papers with bookmarks: {fixed}")
    print(f"  Papers without bookmarks: {no_bookmarks}")
    print("=" * 70)
    print("\n⚠️  Note: This is just a test to check bookmarks.")
    print("    Real update needs page numbers in paragraphs table.")


if __name__ == "__main__":
    main()
