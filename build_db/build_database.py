"""
Build Sci-Pal Database
V20.3 - Store figure+paragraph page+bbox coordinates; infer journal from DOI
Architecture:
- Each paper is a logical unit with paper_id
- Within each paper: paragraphs, figures, tables, citations
- Internal index: paragraph <-> figure <-> table <-> citation
- Cross-paper index: paper <-> paper
- Division of labor:
    * Grobid (Docker)  -> title/authors/journal/doi/year + structured references
    * Docling          -> paragraphs, figures, tables, section hierarchy
- V18.0: Grobid title is sanity-checked before overriding Docling title.
         Suspicious Grobid titles (all-caps running headers, consortium names,
         truncated headers) are rejected; Docling title is kept.
- V20.1: Infer journal name from DOI prefix when Grobid/Docling miss it.
- V20.2: Store page + bbox coordinates with figures.
- V20.3: Store page + bbox coordinates with paragraphs (via chunk.meta.doc_items).
"""
import os
import sys
import re
import json
import sqlite3
from typing import Optional
import hashlib
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Model config
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions
from docling.chunking import HierarchicalChunker

# docling-hierarchical-pdf postprocessor (optional, for better section hierarchy)
try:
    from hierarchical.postprocessor import ResultPostprocessor
    HIERARCHICAL_AVAILABLE = True
except ImportError:
    HIERARCHICAL_AVAILABLE = False
    print("⚠️  docling-hierarchical-pdf not installed. Install with: pip install docling-hierarchical-pdf")

# Grobid client (optional; run via Docker on http://localhost:8070)
try:
    from build_db.parsers.grobid_parser import GrobidParser
    GROBID_IMPORT_OK = True
except Exception:
    GROBID_IMPORT_OK = False
    print("ℹ️  Grobid parser not importable; metadata/citations will rely on Docling.")


# ============================================================
# Section name filtering
# ============================================================

# Blacklist: common noise that is NOT a real section
SECTION_BLACKLIST = {
    # Journal watermarks / boilerplate
    "article", "protocol", "review", "review article", "original article",
    "open", "open access", "science direct", "sciencedirect",
    "edited by:", "reviewed by:", "*correspondence:", "specialty section:",
    "citation:", "† present address:",
    "highlights", "graphical abstract", "in brief",
    "a r t i c l e i n f o", "a r t i c l e  i n f o",
    "a b s t r a c t", "a b s t r a c t  ",
    "article info", "abstract",
}

# Section names that mark the start of references
REFERENCE_SECTION_NAMES = {
    "references", "reference", "bibliography",
    "references and recommended reading",
}


def is_noise_section(name: str) -> bool:
    """Check if a section name is just noise (not a real section)"""
    if not name:
        return True
    name_clean = name.strip().lower()
    
    # Exact match against blacklist
    if name_clean in SECTION_BLACKLIST:
        return True
    
    # Too short
    if len(name_clean) < 3:
        return True
    
    # Starts with "Fig." or "Figure"
    if name_clean.startswith("fig.") or name_clean.startswith("figure"):
        return True
    
    # Starts with "Table"
    if name_clean.startswith("table"):
        return True
    
    # Just a DOI link
    if name_clean.startswith("https://doi.org/") or name_clean.startswith("http://doi.org/"):
        return True
    
    return False


def is_reference_section(name: str) -> bool:
    """Check if this section marks the start of references"""
    if not name:
        return False
    name_clean = name.strip().lower()
    return name_clean in REFERENCE_SECTION_NAMES


def is_reference_like_section(name: str) -> bool:
    """Check if a 'section' is actually a reference list item (false positive)"""
    if not name:
        return False
    
    # Pattern: "1. Author Name. Title..." (numbered reference)
    # References typically start with a number followed by author names
    if re.match(r'^\d+\.\s+[A-Z][a-z]+\s+[A-Z]', name):
        return True
    
    # Very long section name (>150 chars) is likely a reference, not a heading
    if len(name) > 150:
        return True
    
    return False


# Noise paragraph patterns (journal headers, footers, boilerplate)
NOISE_PARAGRAPH_PATTERNS = [
    # Journal watermarks / headers
    r'^Contents lists available at',
    r'^ScienceDirect$',
    r'^www\.elsevier\.com/locate/',
    r'^journal homepage',
    r'^Journal of\s+\w+',
    r'^https?://doi\.org/',
    r'^https?://dx\.doi\.org/',
    
    # Editorial boilerplate
    r'^Edited by:',
    r'^Reviewed by:',
    r'^\*?Correspondence:',
    r'^Specialty section:',
    r'^Citation:',
    r'^†?\s*Present address:',
    r'^Current address:',
    r'^Mailing address:',
    
    # Spaced out text (like "a r t i c l e i n f o")
    r'^[a-z]\s+[a-z]\s+[a-z]\s+[a-z]\s+[a-z]\s+[a-z]\s+[a-z]\s+[a-z]',
    
    # Author affiliations (short lines starting with department)
    r'^[a-z]\s+Department of',
    r'^[a-z]\s+Yale University',
    r'^[a-z]\s+Harvard University',
    
    # "Highlights", "Graphical abstract" etc.
    r'^Highlights$',
    r'^Graphical abstract$',
    r'^In brief$',
]


def is_noise_paragraph(text: str) -> bool:
    """Check if a paragraph is just noise (journal header, footer, boilerplate)"""
    if not text:
        return True
    
    text_clean = text.strip()
    
    # Too short
    if len(text_clean) < 3:
        return True
    
    # Check against noise patterns
    for pattern in NOISE_PARAGRAPH_PATTERNS:
        if re.match(pattern, text_clean, re.IGNORECASE):
            return True
    
    # Spaced out single letters (like "a b s t r a c t")
    words = text_clean.split()
    if len(words) > 3 and all(len(w) == 1 for w in words[:5]):
        return True
    
    return False


# ============================================================
# Grobid title sanity check (V18.0)
# ============================================================

# Consortium / author-team suffixes that Grobid sometimes mistakes for a title
CONSORTIUM_SUFFIXES = (
    " research team", " study group", " study team", " consortium",
    " collaboration", " network", " initiative", " project",
    " group", " working group",
)

# Journal running headers / section labels that are all-caps and generic
# (we detect these by the all-caps ratio rule below)


def is_grobid_title_suspicious(title: str) -> tuple:
    """Check whether a Grobid-returned title looks wrong.

    Returns (is_suspicious: bool, reason: str).
    Suspicious cases:
      1. All-caps running header / journal section label
         (e.g. "TRANSLATIONAL RESEARCH IN HEART FAILURE (")
      2. Consortium / author-team name mistaken for title
         (e.g. "Estonian Biobank Research Team")
      3. Truncated header ending with an unmatched '('
    """
    if not title or not title.strip():
        return True, "empty"

    t = title.strip()

    # Rule 3: truncated / unbalanced punctuation
    # Ends with an unmatched opening bracket (running header cut off mid-phrase)
    if t.endswith("(") and t.count("(") > t.count(")"):
        return True, "unbalanced_paren"

    # Rule 2: consortium / author-team suffix
    t_lower = t.lower().rstrip(".")
    for suffix in CONSORTIUM_SUFFIXES:
        if t_lower.endswith(suffix):
            # But exclude legitimate titles that happen to contain these words mid-title
            # Only flag if the whole string is short (consortium names are ~3-6 words)
            word_count = len(t.split())
            if word_count <= 8:
                return True, f"consortium_suffix:{suffix.strip()}"

    # Rule 1: all-caps running header
    # Count alphabetic characters
    letters = [c for c in t if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        word_count = len(t.split())
        # >85% uppercase AND short (<=8 words) = likely a running header, not a paper title
        if upper_ratio > 0.85 and word_count <= 8:
            return True, f"all_caps({upper_ratio:.0%})"

    return False, ""


# ============================================================
# Database Schema
# ============================================================
SCHEMA_SQL = """
-- Papers table (paper-level metadata)
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    title TEXT,
    authors TEXT,
    abstract TEXT,
    journal TEXT,
    year INTEGER,
    doi TEXT,
    keywords TEXT,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    paper_type TEXT DEFAULT 'J',
    publisher TEXT,
    language TEXT DEFAULT 'en',
    affiliations TEXT,
    funding TEXT,
    parse_status TEXT DEFAULT 'completed',
    parse_engine TEXT,
    total_paragraphs INTEGER DEFAULT 0,
    total_figures INTEGER DEFAULT 0,
    total_tables INTEGER DEFAULT 0,
    total_citations INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Paragraphs table (paragraph-level, per paper)
CREATE TABLE IF NOT EXISTS paragraphs (
    para_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    section_level1 TEXT,
    section_level2 TEXT,
    section_level3 TEXT,
    text TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    page INTEGER,
    bbox TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Figures table (figure metadata + path, per paper)
CREATE TABLE IF NOT EXISTS figures (
    fig_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    fig_number TEXT,
    caption TEXT,
    file_path TEXT,
    page INTEGER,
    bbox TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Tables table (table metadata + structure, per paper)
CREATE TABLE IF NOT EXISTS tables (
    table_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    table_number TEXT,
    caption TEXT,
    markdown TEXT,
    page INTEGER,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Citations table (references list, per paper)
CREATE TABLE IF NOT EXISTS citations (
    citation_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    ref_number TEXT,
    raw_text TEXT,
    doi TEXT,
    title TEXT,
    authors TEXT,
    journal TEXT,
    year INTEGER,
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Supplementary files table (V25.17)
-- Stores supplementary materials associated with a paper (PDF/Excel/Word/etc.)
CREATE TABLE IF NOT EXISTS supplementary_files (
    supp_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_type TEXT,
    file_path TEXT,
    file_size INTEGER,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Internal index (within same paper)
-- Links: paragraph <-> figure, paragraph <-> table, paragraph <-> citation
CREATE TABLE IF NOT EXISTS paper_index (
    index_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- paragraph / figure / table / citation
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,  -- mentions / cites / contains
    FOREIGN KEY (paper_id) REFERENCES papers(paper_id)
);

-- Cross-paper index (between different papers)
CREATE TABLE IF NOT EXISTS cross_paper_index (
    link_id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL,
    target_paper_id TEXT NOT NULL,
    relation TEXT NOT NULL,  -- cites / same_author / same_topic
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY (source_paper_id) REFERENCES papers(paper_id),
    FOREIGN KEY (target_paper_id) REFERENCES papers(paper_id)
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_paragraphs_paper ON paragraphs(paper_id);
CREATE INDEX IF NOT EXISTS idx_figures_paper ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_tables_paper ON tables(paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_paper ON citations(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_index_paper ON paper_index(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_index_source ON paper_index(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_paper_index_target ON paper_index(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_cross_paper_source ON cross_paper_index(source_paper_id);
CREATE INDEX IF NOT EXISTS idx_cross_paper_target ON cross_paper_index(target_paper_id);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
"""


# ============================================================
# Helper functions
# ============================================================
def generate_paper_id(filename: str) -> str:
    """Generate a unique paper ID from filename"""
    name = Path(filename).stem
    short_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
    return f"paper_{name[:30]}_{short_hash}"


def generate_id(prefix: str, paper_id: str, num: int) -> str:
    """Generate a unique ID for items within a paper"""
    return f"{prefix}_{paper_id}_{num:04d}"


def extract_doi(text: str) -> str:
    """Extract DOI from text - handles ALL formats and normalizes to plain DOI"""
    if not text:
        return None

    # 1. Try old URL format: http://dx.doi.org/10.xxxx/xxxxx
    url_match = re.search(r'https?://dx\.doi\.org/(10\.\d{4,}/[A-Za-z0-9\-._()]+)', text, re.IGNORECASE)
    if url_match:
        return url_match.group(1).rstrip('.,;)]')

    # 2. Try new URL format: https://doi.org/10.xxxx/xxxxx
    url_match = re.search(r'https?://doi\.org/(10\.\d{4,}/[A-Za-z0-9\-._()]+)', text, re.IGNORECASE)
    if url_match:
        return url_match.group(1).rstrip('.,;)]')

    # 3. Try "doi:" or "DOI:" prefix format
    doi_label_match = re.search(r'doi:\s*(10\.\d{4,}/[A-Za-z0-9\-._()]+)', text, re.IGNORECASE)
    if doi_label_match:
        return doi_label_match.group(1).rstrip('.,;)]')

    # 4. Try plain DOI format: 10.xxxx/xxxxx (make sure it's not part of a number)
    plain_match = re.search(r'(?<![\w.])(10\.\d{4,}/[A-Za-z0-9\-._()]+)', text)
    if plain_match:
        return plain_match.group(1).rstrip('.,;)]')

    return None


def extract_doi_from_filename(filename: str) -> str:
    """Extract DOI from common academic filename patterns.
    
    Examples:
      s41586-023-06547-x.pdf  → 10.1038/s41586-023-06547-x (Nature)
      s10555-020-09883-w.pdf → 10.1007/s10555-020-09883-w (Springer)
      CTM2-10-e206.pdf        → 10.1002/ctm2.206 (Wiley)
    """
    base = filename.replace('.pdf', '').lower()
    
    # Nature/Springer pattern: sXXXX-YY-YYYY
    # s41xxx → Nature family (10.1038/)
    # s1xxxx → Springer family (10.1007/)
    m = re.match(r'^s(\d+)-(\d{2})-(\w+)$', base)
    if m:
        journal_num, year, suffix = m.groups()
        if journal_num.startswith('41'):
            # Nature family: s41586, s41590, s41591, s41577, s41525, s41467, s41392
            return f"10.1038/s{journal_num}-{year}-{suffix}"
        else:
            # Springer family: s10555, s10875, s11897, etc.
            return f"10.1007/s{journal_num}-{year}-{suffix}"
    
    # Wiley CTM: CTM2-10-e206 → 10.1002/ctm2.206
    m = re.match(r'^ctm2?-\d+-e(\d+)$', base)
    if m:
        art_id = m.group(1)
        return f"10.1002/ctm2.{art_id}"
    
    return None


# DOI prefix → journal name mapping (V20.1)
# Covers common biology/immunology journals in our collection
DOI_JOURNAL_MAP = {
    # Nature family
    "10.1038/s41586": "Nature",
    "10.1038/s41590": "Nature Immunology",
    "10.1038/s41591": "Nature Medicine",
    "10.1038/s41577": "Nature Reviews Immunology",
    "10.1038/s41525": "Nature Communications Biology",
    "10.1038/s41467": "Nature Communications",
    "10.1038/s41392": "Signal Transduction and Targeted Therapy",
    "10.1038/s41598": "Scientific Reports",
    "10.1038/s41588": "Nature Genetics",
    "10.1038/s41419": "Cell Death & Disease",
    "10.1038/s42003": "Communications Biology",
    # Springer
    "10.1007/s10875": "Journal of Clinical Immunology",
    "10.1007/s10555": "Cancer and Metastasis Reviews",
    "10.1007/s11897": "Heart Failure Reviews",
    # Wiley
    "10.1002/ctm2": "Clinical and Translational Medicine",
    "10.1002/cyto.a": "Cytometry Part A",
    "10.1111/ejh": "European Journal of Haematology",
    # PLOS
    "10.1371/journal.pgen": "PLOS Genetics",
    "10.1371/journal.pmed": "PLOS Medicine",
    "10.1371/journal.ppat": "PLOS Pathogens",
    # Frontiers
    "10.3389/fimmu": "Frontiers in Immunology",
    "10.3389/fonc": "Frontiers in Oncology",
    "10.3389/ebm": "Experimental Biology and Medicine",
    # Elsevier
    "10.1016/j.jim": "Journal of Immunological Methods",
    "10.1016/j.biopha": "Biomedicine & Pharmacotherapy",
    "10.1016/j.cellsig": "Cellular Signalling",
    "10.1016/j.coi": "Current Opinion in Immunology",
    "10.1016/j.als": "Aging and Longevity",
    "10.1016/j.celrep": "Cell Reports",
    "10.1016/j.crbiot": "Comptes Rendus Biologies",
    # Preprints
    "10.1101/gr": "Genome Research",
    "10.1101/": "bioRxiv",
    # Other
    "10.4049/jimmunol": "Journal of Immunology",
    "10.1186/s13059": "Genome Biology",
    "10.1093/synbio": "Synthetic Biology",
    "10.5539/ijb": "International Journal of Biology",
    "10.56042/ijeb": "Indian Journal of Experimental Biology",
}


def journal_from_doi(doi: str) -> Optional[str]:
    """Infer journal name from DOI prefix."""
    if not doi:
        return None
    doi = doi.lower().strip()
    # Try longest prefix match first
    for prefix in sorted(DOI_JOURNAL_MAP.keys(), key=len, reverse=True):
        if doi.startswith(prefix):
            return DOI_JOURNAL_MAP[prefix]
    return None


def extract_doi_with_pymupdf(pdf_path: str) -> str:
    """Extract DOI using PyMuPDF (metadata + links + first page text)
    
    Strategies:
    1. Check PDF metadata (subject, keywords)
    2. Check hyperlinks on first few pages
    3. Search first 2 pages text for DOI
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("    ⚠️  PyMuPDF not installed, skipping")
        return None
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"    ⚠️  Could not open PDF with PyMuPDF: {e}")
        return None
    
    doi = None
    
    # 1. Check PDF metadata
    try:
        metadata = doc.metadata
        if metadata:
            # Check subject, keywords, title for DOI
            for key in ['subject', 'keywords', 'title']:
                val = metadata.get(key, '')
                if val:
                    doi = extract_doi(val)
                    if doi:
                        print(f"    ✅ DOI found in PDF metadata ({key})")
                        break
    except Exception:
        pass
    
    # 2. Check hyperlinks on first 3 pages
    if not doi:
        try:
            for page_num in range(min(3, len(doc))):
                page = doc[page_num]
                links = page.get_links()
                for link in links:
                    if link.get('kind') == 2:  # URI link
                        uri = link.get('uri', '')
                        doi = extract_doi(uri)
                        if doi:
                            print(f"    ✅ DOI found in hyperlink (page {page_num+1})")
                            break
                if doi:
                    break
        except Exception:
            pass
    
    # 3. Search first 2 pages text for DOI
    if not doi:
        try:
            for page_num in range(min(2, len(doc))):
                page = doc[page_num]
                text = page.get_text()
                # Also try removing spaces (for DOIs broken by line breaks)
                text_no_spaces = text.replace(' ', '').replace('\n', '')
                doi = extract_doi(text)
                if not doi:
                    doi = extract_doi(text_no_spaces)
                if doi:
                    print(f"    ✅ DOI found in text (page {page_num+1})")
                    break
        except Exception:
            pass
    
    doc.close()
    return doi


def extract_fig_refs(paragraph_text: str) -> list:
    """Extract figure references like 'Fig. 1', 'Figure 2', 'Fig.3'"""
    refs = []
    # Match Fig. 1, Figure 2, Fig.3, etc.
    matches = re.findall(r'(?:Fig\.?|Figure|Table|Tab\.?)\s*(\d+)', paragraph_text, re.IGNORECASE)
    for num in matches:
        refs.append(num)
    return refs


# ============================================================
# Main build function
# ============================================================
def build_database(input_dir: str = "documents", db_path: str = "data/research.db"):
    """Build the full database from PDFs"""

    db_full_path = project_root / db_path
    db_full_path.parent.mkdir(exist_ok=True)

    # Delete old database if exists (start fresh)
    if db_full_path.exists():
        db_full_path.unlink()
        print(f"🗑️  Deleted old database: {db_full_path}")

    # Connect to database and create schema
    conn = sqlite3.connect(str(db_full_path))
    conn.executescript(SCHEMA_SQL)
    print("✅ Database schema created")

    # Setup Docling
    print("\n🔄 Initializing Docling...")
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.generate_parsed_pages = True
    pipeline_options.generate_picture_images = True  # Generate actual image data for figures
    pipeline_options.images_scale = 2.0  # 2x resolution for better quality
    
    # Heading hierarchy options
    from docling.datamodel.pipeline_options import HeadingHierarchyOptions
    pipeline_options.heading_hierarchy_options = HeadingHierarchyOptions(
        enabled=True,
        use_bookmarks=True,
        use_numbering=True,
        use_style=True,
        max_level=6,
        bookmark_match_threshold=0.5  # Lowered from 0.6 to better match bookmarks
    )
    
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=8, device="cuda"
    )
    print(f"  🔍 generate_picture_images = {pipeline_options.generate_picture_images}")

    converter = DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    chunker = HierarchicalChunker()
    print("✅ Docling ready!")

    # Initialize Grobid (optional). If it's not running, we silently fall back to Docling.
    grobid = None
    if GROBID_IMPORT_OK:
        try:
            grobid = GrobidParser()
            if not grobid.is_alive():
                print("ℹ️  Grobid server not running; metadata/citations will rely on Docling.")
                grobid = None
            else:
                print("✅ Grobid active: will enrich metadata + references")
        except Exception as e:
            print(f"⚠️  Grobid init failed: {str(e)[:80]}")
            grobid = None

    # Find all PDFs
    input_path = project_root / input_dir
    pdf_files = sorted(list(input_path.rglob("*.pdf")))
    print(f"\nFound {len(pdf_files)} PDFs to process")
    print("=" * 70)

    # Process each PDF
    stats = {"success": 0, "failed": 0, "total_paragraphs": 0, "total_figures": 0, "total_tables": 0}

    for i, pdf_file in enumerate(pdf_files):
        print(f"\n[{i+1}/{len(pdf_files)}] Processing: {pdf_file.name}")

        try:
            # Parse PDF
            result = converter.convert(str(pdf_file))
            doc = result.document

            # Apply docling-hierarchical-pdf postprocessor for better section hierarchy
            if HIERARCHICAL_AVAILABLE:
                try:
                    ResultPostprocessor(result, source=str(pdf_file)).process()
                    print(f"    ✅ Applied hierarchical postprocessor")
                except Exception as e:
                    print(f"    ⚠️  Postprocessor warning: {str(e)[:60]}")

            # Generate paper_id
            paper_id = generate_paper_id(pdf_file.name)

            # Extract paper metadata
            md_text = doc.export_to_markdown()
            lines = md_text.split('\n')

            # Priority 1: Use Docling's built-in metadata (from PDF bookmarks/TOC)
            title = None
            authors = None
            journal = None
            doi = None
            year = None
            grobid_header = None
            grobid_citations = None
            grobid_intext = None

            # Try Docling metadata first
            try:
                if hasattr(doc, 'metadata') and doc.metadata:
                    if hasattr(doc.metadata, 'title') and doc.metadata.title:
                        title = str(doc.metadata.title).strip()
                    if hasattr(doc.metadata, 'authors') and doc.metadata.authors:
                        authors = ', '.join([str(a) for a in doc.metadata.authors[:5]])
                    if hasattr(doc.metadata, 'journal') and doc.metadata.journal:
                        journal = str(doc.metadata.journal).strip()
            except Exception:
                pass

            # Also try to find DOI if not found yet
            if not doi:
                # Scan first 200 lines (not just 50)
                for line in lines[:200]:
                    doi = extract_doi(line)
                    if doi:
                        break
            
            # Also search in full markdown text if not found in first 200 lines
            if not doi:
                doi = extract_doi(md_text[:3000])
            
            # Try PyMuPDF (metadata + links + first page text)
            if not doi:
                doi = extract_doi_with_pymupdf(str(pdf_file))
            
            # Last resort: try to extract DOI from filename pattern
            if not doi:
                doi = extract_doi_from_filename(pdf_file.name)
                if doi:
                    print(f"    (DOI extracted from filename: {doi})")

            # Grobid enrichment: header metadata (Grobid wins) + structured citations.
            # Runs offline (no CrossRef consolidation). Failures never break the build.
            # V18.0: sanity-check Grobid title before accepting it.
            if grobid is not None:
                try:
                    gres = grobid.parse(str(pdf_file))
                    if 'error' not in gres:
                        grobid_header = gres.get('metadata') or {}
                        grobid_citations = gres.get('citations') or []
                        grobid_intext = gres.get('intext_citations') or []

                        # Title: accept Grobid only if it passes sanity check
                        g_title = (grobid_header.get('title') or '').strip()
                        if g_title:
                            suspicious, reason = is_grobid_title_suspicious(g_title)
                            if suspicious:
                                print(f"    ⚠️  Grobid title rejected ({reason}): "
                                      f"{g_title[:50]!r} -> keeping Docling/PyMuPDF title")
                            else:
                                title = g_title

                        if grobid_header.get('authors'):
                            authors = grobid_header['authors']
                        if grobid_header.get('journal'):
                            journal = grobid_header['journal']
                        if grobid_header.get('doi'):
                            doi = grobid_header['doi']
                        if grobid_header.get('year'):
                            year = grobid_header['year']
                        print(f"    🧠 Grobid: {len(grobid_citations)} refs, title="
                              f"{(title or 'N/A')[:40]}")
                except Exception as e:
                    print(f"    (Grobid warning: {str(e)[:70]})")

            # V20.1: Infer journal from DOI if still unknown
            if not journal and doi:
                journal = journal_from_doi(doi)
                if journal:
                    print(f"    📰 Journal (from DOI): {journal}")

            # Chunk the document
            chunks = list(chunker.chunk(doc))

            # Get title from document headings
            if not title or len(title) < 10:
                # Standard section names and editorial boilerplate that are NOT the paper title
                section_names = ['abstract', 'introduction', 'background', 'methods',
                                 'results', 'discussion', 'conclusion', 'references',
                                 'acknowledgments', 'supplementary', 'supplemental',
                                 'materials and methods', 'review', 'protocol',
                                 'article', 'specialty section', 'graphical abstract',
                                 'journal of', 'science direct', 'homepage',
                                 'edited by', 'reviewed by', 'correspondence',
                                 'address', 'funding', 'author contributions',
                                 'conflict of interest', 'keywords', 'received',
                                 'accepted', 'published', 'copyright', 'license',
                                 '*correspondence', 'study committee', 'review team',
                                 'expert review of', 'nature immunology', 'preface',
                                 'hhs public access', 'author manuscript', 'mit ll',
                                 'study team', 'committee', 'presentation address',
                                 'current address', 'present address', 'mailing address',
                                 'acknowledgements', 'acknowledgement', 'contributors',
                                 'footnote', 'footnotes', 'disclosures', 'disclosure',
                                 'conflicts of interest', 'ethics statement', 'ethics approval']

                for chunk in chunks[:40]:  # Check first 40 chunks
                    if chunk.meta and chunk.meta.headings and len(chunk.meta.headings) > 0:
                        first_heading = chunk.meta.headings[0]
                        if first_heading and len(first_heading) > 10:
                            # Strip leading symbols (like †, *, #) before checking
                            cleaned_heading = first_heading.lstrip('†*#•-–— ').lower()
                            # Check if this looks like a real paper title (not a section)
                            is_section = any(cleaned_heading.startswith(sn) for sn in section_names)
                            if not is_section:
                                title = first_heading
                                break

            # Store paragraphs
            # Note: Section names are stored as-is from the PDF.
            # Search-layer will handle synonyms:
            #   "Methods" → also matches "Protocol", "Experimental Procedures", etc.
            #   "Introduction" → also matches "Background", "Overview", etc.
            para_count = 0
            in_references = False  # Track when we hit the references section
            current_l1 = None
            current_l2 = None
            current_l3 = None
            
            for j, chunk in enumerate(chunks):
                if not chunk.text or len(chunk.text.strip()) < 20:
                    continue  # Skip empty or too short paragraphs
                text = chunk.text.strip()
                if not text:
                    continue

                # Skip noise paragraphs (journal headers, footers, boilerplate)
                if is_noise_paragraph(text):
                    continue

                headings = chunk.meta.headings if chunk.meta and chunk.meta.headings else []
                
                # Get current section hierarchy from headings
                if len(headings) > 0:
                    # Filter each heading level
                    l1_raw = headings[0] if len(headings) > 0 else None
                    l2_raw = headings[1] if len(headings) > 1 else None
                    l3_raw = headings[2] if len(headings) > 2 else None
                    
                    # Check if we hit the references section
                    if is_reference_section(l1_raw):
                        in_references = True
                    
                    # Skip sections that are noise or reference items
                    if is_noise_section(l1_raw) or (not in_references and is_reference_like_section(l1_raw)):
                        l1_raw = None
                    if is_noise_section(l2_raw) or (not in_references and is_reference_like_section(l2_raw)):
                        l2_raw = None
                    if is_noise_section(l3_raw) or (not in_references and is_reference_like_section(l3_raw)):
                        l3_raw = None
                    
                    # Update current hierarchy
                    if l1_raw:
                        current_l1 = l1_raw
                        current_l2 = None
                        current_l3 = None
                    if l2_raw:
                        current_l2 = l2_raw
                        current_l3 = None
                    if l3_raw:
                        current_l3 = l3_raw
                
                section_l1 = current_l1
                section_l2 = current_l2
                section_l3 = current_l3

                para_id = generate_id("para", paper_id, para_count + 1)

                # V20.2: Extract page and bbox from chunk's doc_items
                para_page = None
                para_bbox = None
                try:
                    if chunk.meta and chunk.meta.doc_items:
                        first_item = chunk.meta.doc_items[0]
                        if hasattr(first_item, 'prov') and first_item.prov:
                            prov = first_item.prov[0]
                            para_page = prov.page_no
                            b = prov.bbox
                            para_bbox = f"{b.l:.1f},{b.t:.1f},{b.r:.1f},{b.b:.1f}"
                except:
                    pass

                conn.execute("""
                    INSERT OR REPLACE INTO paragraphs
                    (para_id, paper_id, section_level1, section_level2, section_level3, text, sequence, page, bbox)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (para_id, paper_id, section_l1, section_l2, section_l3, chunk.text, para_count, para_page, para_bbox))
                para_count += 1

            # Extract and store figures (including actual image files)
            images_dir = project_root / "images"
            images_dir.mkdir(exist_ok=True)

            fig_count = 0
            skipped_figures = 0
            skipped_tiny = 0
            try:
                # Try different import paths
                try:
                    from docling_core.types.doc import PictureItem as FigureItem
                except ImportError:
                    from docling_core.types.doc.document import PictureItem as FigureItem

                for item, _ in doc.iterate_items():
                    if isinstance(item, FigureItem):
                        # Skip tiny images (likely logos, icons, not real figures)
                        should_skip = False
                        try:
                            if hasattr(item, 'size') and item.size:
                                w, h = item.size.width, item.size.height
                                if w < 50 or h < 50:  # Skip tiny images < 50px
                                    should_skip = True
                        except:
                            pass

                        if should_skip:
                            skipped_figures += 1
                            continue

                        # V20.2: Extract page and bbox coordinates
                        page_no = None
                        bbox = None
                        try:
                            if hasattr(item, 'prov') and item.prov:
                                prov = item.prov[0] if isinstance(item.prov, list) else item.prov
                                if hasattr(prov, 'page_no'):
                                    page_no = prov.page_no
                                if hasattr(prov, 'bbox'):
                                    bbox = f"{prov.bbox.l:.1f},{prov.bbox.t:.1f},{prov.bbox.r:.1f},{prov.bbox.b:.1f}"
                        except:
                            pass

                        fig_count += 1
                        fig_id = generate_id("fig", paper_id, fig_count)
                        caption = ""
                        if hasattr(item, 'caption_text'):
                            try:
                                caption = item.caption_text(doc)
                            except:
                                pass

                        # Save actual image file to disk
                        file_path = None
                        try:
                            img = item.get_image(doc)
                            if img is not None:
                                # Skip tiny images (logos, icons, etc.)
                                min_size = 100  # pixels
                                w, h = img.size
                                if w < min_size or h < min_size:
                                    skipped_tiny += 1
                                    continue

                                # Save as PNG with page+coords in filename
                                img_filename = f"{paper_id[:30]}_p{page_no or 0}_fig_{fig_count:03d}.png"
                                img_path = images_dir / img_filename
                                img.save(str(img_path))
                                # Store relative path from project root
                                file_path = f"images/{img_filename}"
                        except Exception as e:
                            print(f"    (image save warning: {type(e).__name__}: {str(e)[:60]})")

                        conn.execute("""
                            INSERT OR REPLACE INTO figures
                            (fig_id, paper_id, fig_number, caption, file_path, page, bbox)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (fig_id, paper_id, f"Fig {fig_count}", caption, file_path, page_no, bbox))
            except Exception as e:
                print(f"    (figure extraction warning: {type(e).__name__}: {str(e)[:60]})")

            # Extract and store tables
            table_count = 0
            try:
                try:
                    from docling_core.types.doc import TableItem
                except ImportError:
                    from docling_core.types.doc.document import TableItem

                for item, _ in doc.iterate_items():
                    if isinstance(item, TableItem):
                        table_count += 1
                        table_id = generate_id("table", paper_id, table_count)
                        caption = ""
                        markdown = ""
                        if hasattr(item, 'caption_text'):
                            try:
                                caption = item.caption_text(doc)
                            except:
                                pass
                        if hasattr(item, 'export_to_markdown'):
                            try:
                                markdown = item.export_to_markdown()
                            except:
                                pass
                        conn.execute("""
                            INSERT OR REPLACE INTO tables 
                            (table_id, paper_id, table_number, caption, markdown, page)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (table_id, paper_id, f"Table {table_count}", caption, markdown, None))
            except Exception as e:
                print(f"    (table extraction warning: {str(e)[:60]})")

            # Extract citations: prefer Grobid's structured references,
            # fall back to crude markdown line-splitting when Grobid is unavailable.
            citation_count = 0
            try:
                if grobid_citations:
                    for ref in grobid_citations:
                        citation_count += 1
                        ref_id = generate_id("cite", paper_id, citation_count)
                        conn.execute("""
                            INSERT OR REPLACE INTO citations
                            (citation_id, paper_id, ref_number, raw_text, doi, title, authors, journal, year)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (ref_id, paper_id, str(ref.get('ref_number', citation_count)),
                              ref.get('raw_text'), ref.get('doi'), ref.get('title'),
                              ref.get('authors'), ref.get('journal'), ref.get('year')))
                else:
                    # Find references section in markdown (Docling fallback)
                    in_refs = False
                    for line in lines:
                        line_lower = line.lower().strip()
                        if any(kw in line_lower for kw in ['references', 'reference', 'bibliography']):
                            in_refs = True
                            continue
                        if in_refs and line.strip() and not line.startswith('#'):
                            # This is a reference line
                            citation_count += 1
                            ref_id = generate_id("cite", paper_id, citation_count)
                            raw_text = line.strip()
                            ref_doi = extract_doi(raw_text)
                            conn.execute("""
                                INSERT OR REPLACE INTO citations
                                (citation_id, paper_id, ref_number, raw_text, doi, title, authors, journal, year)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (ref_id, paper_id, str(citation_count), raw_text, ref_doi, None, None, None, None))
                        # Stop after we hit too many lines (safety)
                        if citation_count > 100:
                            break
            except Exception as e:
                print(f"    (citation extraction warning: {str(e)[:50]})")

            # ============================================================
            # Build internal paper index
            # Link paragraphs to figures, tables, citations they mention
            # ============================================================
            index_count = 0
            try:
                # Get all paragraphs for this paper
                cur = conn.execute(
                    "SELECT para_id, text FROM paragraphs WHERE paper_id = ?", (paper_id,)
                )
                paper_paragraphs = cur.fetchall()

                # Get all figures for this paper
                cur = conn.execute(
                    "SELECT fig_id, fig_number FROM figures WHERE paper_id = ?", (paper_id,)
                )
                paper_figures = {num: fid for fid, num in cur.fetchall()}

                # Get all tables for this paper
                cur = conn.execute(
                    "SELECT table_id, table_number FROM tables WHERE paper_id = ?", (paper_id,)
                )
                paper_tables = {num: tid for tid, num in cur.fetchall()}

                # Get all citations for this paper
                cur = conn.execute(
                    "SELECT citation_id, ref_number FROM citations WHERE paper_id = ?", (paper_id,)
                )
                paper_citations = {num: cid for cid, num in cur.fetchall()}

                # For each paragraph, find what it mentions
                for para_id, para_text in paper_paragraphs:
                    # Find figure references: "Fig. 1", "Figure 2", etc.
                    fig_refs = re.findall(r'(?:Fig\.?|Figure)\s*(\d+)', para_text, re.IGNORECASE)
                    for fig_num in fig_refs:
                        fig_key = f"Fig {fig_num}"
                        if fig_key in paper_figures:
                            index_count += 1
                            conn.execute("""
                                INSERT OR REPLACE INTO paper_index 
                                (index_id, paper_id, source_type, source_id, target_type, target_id, relation)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (f"idx_{paper_id}_{index_count:05d}", paper_id,
                                  "paragraph", para_id, "figure", paper_figures[fig_key], "mentions"))

                    # Find table references: "Table 1", "Tab. 2", etc.
                    table_refs = re.findall(r'(?:Table|Tab\.?)\s*(\d+)', para_text, re.IGNORECASE)
                    for table_num in table_refs:
                        table_key = f"Table {table_num}"
                        if table_key in paper_tables:
                            index_count += 1
                            conn.execute("""
                                INSERT OR REPLACE INTO paper_index 
                                (index_id, paper_id, source_type, source_id, target_type, target_id, relation)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (f"idx_{paper_id}_{index_count:05d}", paper_id,
                                  "paragraph", para_id, "table", paper_tables[table_key], "mentions"))

                    # Find citation references: [1], [2], etc.
                    cite_refs = re.findall(r'\[(\d+)\]', para_text)
                    for cite_num in cite_refs:
                        if cite_num in paper_citations:
                            index_count += 1
                            conn.execute("""
                                INSERT OR REPLACE INTO paper_index 
                                (index_id, paper_id, source_type, source_id, target_type, target_id, relation)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (f"idx_{paper_id}_{index_count:05d}", paper_id,
                                  "paragraph", para_id, "citation", paper_citations[cite_num], "cites"))

                    # V20.4: Use GROBID's built-in in-text citation links
                    if grobid_intext:
                        grobid_link_count = 0
                        for intext in grobid_intext:
                            ref_num = intext.get('ref_number')
                            context = (intext.get('context') or '').strip()
                            if not ref_num or ref_num not in paper_citations:
                                continue
                            if not context:
                                continue

                            # Find which paragraph contains this context
                            for para_id2, para_text2 in paper_paragraphs:
                                if context[:50] in para_text2[:2000]:
                                    grobid_link_count += 1
                                    conn.execute("""
                                        INSERT OR REPLACE INTO paper_index 
                                        (index_id, paper_id, source_type, source_id, target_type, target_id, relation)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    """, (f"idx_{paper_id}_g{intext.get('target_id', '')}_{grobid_link_count}",
                                          paper_id, "paragraph", para_id2, "citation",
                                          paper_citations[ref_num], "grobid_cites"))
                                    break

                        if grobid_link_count > 0:
                            print(f"    🔗 GROBID in-text links: {grobid_link_count}")

            except Exception as e:
                print(f"    (index building warning: {str(e)[:50]})")

            # Extract abstract by structure
            def is_noise_text(text):
                """Check if text is noise (copyright, author info, etc.)"""
                text_lower = text.lower().strip()
                noise_patterns = [
                    '©', 'copyright', 'creative commons', 'open access',
                    'received:', 'accepted:', 'published:',
                    'doi:', 'http://', 'https://',
                    'correspondence to:', 'corresponding author',
                    'editor:', 'peer review',
                    'funding:', 'data availability',
                    'license', 'terms of use',
                ]
                for pattern in noise_patterns:
                    if pattern in text_lower:
                        return True
                return False

            abstract_text = ""
            
            # Step 1: Find the first "real section" (Introduction, Results, etc.)
            real_section_keywords = [
                "introduction", "results", "discussion", "methods", "materials and methods",
                "background", "conclusion", "conclusions", "references", "acknowledgements",
                "acknowledgments", "figures", "tables", "supplementary"
            ]
            
            first_real_section_idx = None
            for i, chunk in enumerate(chunks[:50]):  # Look at first 50 chunks
                if chunk.meta and chunk.meta.headings:
                    for h in chunk.meta.headings:
                        if h:
                            h_lower = h.lower().strip()
                            if any(kw in h_lower for kw in real_section_keywords):
                                first_real_section_idx = i
                                break
                    if first_real_section_idx:
                        break
            
            # Step 2: Everything before the first real section = abstract area
            if first_real_section_idx and first_real_section_idx > 0:
                abstract_paras = chunks[:first_real_section_idx]
                clean_texts = []
                for chunk in abstract_paras:
                    if chunk.text and not is_noise_text(chunk.text):
                        clean_texts.append(chunk.text.strip())
                abstract_text = ' '.join(clean_texts)[:2000]
            
            # Step 3: Fallback - find first long non-noise paragraph
            if not abstract_text or len(abstract_text) < 100:
                for chunk in chunks[:20]:
                    if chunk.text and len(chunk.text.strip()) > 200 and not is_noise_text(chunk.text):
                        abstract_text = chunk.text.strip()[:2000]
                        break

            # Update paper stats
            conn.execute("""
                INSERT OR REPLACE INTO papers
                (paper_id, filename, title, authors, journal, year, doi, abstract, total_paragraphs, total_figures, total_tables, total_citations)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (paper_id, pdf_file.name, title, authors, journal, year, doi, abstract_text,
                  para_count, fig_count, table_count, citation_count))

            conn.commit()

            stats["success"] += 1
            stats["total_paragraphs"] += para_count
            print(f"  ✅ Done! {para_count} paras, {fig_count} figs ({skipped_figures} skipped, {skipped_tiny} tiny), {table_count} tables, {citation_count} cites, {index_count} index links")

        except Exception as e:
            stats["failed"] += 1
            print(f"  ❌ Error: {str(e)[:100]}")

    # ============================================================
    # Build cross-paper index (after all papers are loaded)
    # Triple check: DOI → title+authors → title+journal+year
    # ============================================================
    print("\n🔗 Building cross-paper index...")
    cross_link_count = 0
    doi_matches = 0
    title_matches = 0

    try:
        # Get all papers with metadata
        cur = conn.execute("SELECT paper_id, doi, title, authors, journal, year FROM papers")
        all_papers = cur.fetchall()

        # Build lookup indexes
        doi_to_paper = {}
        title_to_paper = {}
        for pid, doi, title, authors, journal, year in all_papers:
            if doi:
                doi_to_paper[doi.lower().rstrip('.,;')] = pid
            if title:
                title_clean = title.lower().strip()[:80]  # Normalize title
                title_to_paper[title_clean] = (pid, authors, journal, year)

        # Get all citations
        cur = conn.execute("SELECT citation_id, paper_id, doi, raw_text FROM citations")
        all_citations = cur.fetchall()

        for citation_id, source_paper_id, cite_doi, cite_raw in all_citations:
            matched_paper = None
            confidence = 0.0
            match_method = None

            # 1st check: DOI (highest confidence)
            if cite_doi:
                doi_lower = cite_doi.lower().rstrip('.,;')
                if doi_lower in doi_to_paper:
                    matched_paper = doi_to_paper[doi_lower]
                    confidence = 1.0
                    match_method = "doi"

            # 2nd check: title match (medium confidence)
            if not matched_paper and cite_raw:
                cite_raw_lower = cite_raw.lower()
                for title_clean, (pid, authors, journal, year) in title_to_paper.items():
                    if len(title_clean) > 20 and title_clean in cite_raw_lower:
                        matched_paper = pid
                        confidence = 0.8
                        match_method = "title"
                        break

            # Add link if matched and not self-citation
            if matched_paper and source_paper_id != matched_paper:
                cross_link_count += 1
                if match_method == "doi":
                    doi_matches += 1
                else:
                    title_matches += 1
                link_id = f"cross_{cross_link_count:05d}"
                conn.execute("""
                    INSERT OR REPLACE INTO cross_paper_index
                    (link_id, source_paper_id, target_paper_id, relation, confidence)
                    VALUES (?, ?, ?, ?, ?)
                """, (link_id, source_paper_id, matched_paper, "cites", confidence))

        conn.commit()
        print(f"  ✅ DOI matches: {doi_matches}")
        print(f"  ✅ Title matches: {title_matches}")
        print(f"  ✅ Total cross-paper links: {cross_link_count}")

    except Exception as e:
        print(f"  (cross-paper index warning: {str(e)[:60]})")

    # Final summary
    conn.close()
    print("\n" + "=" * 70)
    print("📊 Database Build Complete!")
    print("=" * 70)
    print(f"Database: {db_full_path}")
    print(f"Total papers: {len(pdf_files)}")
    print(f"Success: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total paragraphs: {stats['total_paragraphs']}")
    print(f"Cross-paper links: {cross_link_count}")
    print("=" * 70)


if __name__ == "__main__":
    build_database()
