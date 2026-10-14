"""
Parser Orchestrator
V3 Architecture: Docling primary + GROBID enrichment (optional)
- Docling: paragraphs, figures, tables, section hierarchy
- GROBID: metadata (title/authors/journal/doi/year) + structured citations
- GROBID is optional: if service not running, silently fall back to Docling only
- V25.16: Re-integrated GROBID (was deferred in V2) to fix citations=0 issue
"""
import os
import hashlib
from typing import Dict, List, Any, Optional
from .docling_parser import DoclingParser

# Try to import GROBID parser (optional)
GROBID_AVAILABLE = False
GrobidParser = None
try:
    from .grobid_parser import GrobidParser
    GROBID_AVAILABLE = True
except Exception as e:
    print(f"ℹ️  GROBID parser not importable: {e}")
    print("   Metadata/citations will rely on Docling only.")


# ============================================================
# Title sanity check (ported from build_database.py V18.0)
# Prevents GROBID from returning running headers / consortium names as title
# ============================================================

CONSORTIUM_SUFFIXES = (
    " research team", " study group", " study team", " consortium",
    " collaboration", " network", " initiative", " project",
    " group", " working group",
)


def is_grobid_title_suspicious(title: str) -> tuple:
    """Check whether a GROBID-returned title looks wrong.
    Returns (is_suspicious: bool, reason: str).
    """
    if not title:
        return True, "empty title"

    t = title.strip()

    # 1. All-caps running header / journal section label
    alpha_chars = [c for c in t if c.isalpha()]
    if len(alpha_chars) >= 8:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.85:
            return True, f"all-caps (upper ratio {upper_ratio:.0%})"

    # 2. Consortium / author-team suffix
    lower = t.lower()
    for suffix in CONSORTIUM_SUFFIXES:
        if lower.endswith(suffix):
            return True, f"ends with consortium suffix '{suffix}'"

    # 3. Truncated header (ends with '(' or '-' or '—' without closing)
    if t.endswith('(') or t.endswith('-') or t.endswith('—'):
        return True, "truncated (ends with open bracket/dash)"

    # 4. Too short (< 10 chars) likely a label, not a title
    if len(t) < 10:
        return True, f"too short ({len(t)} chars)"

    return False, ""


def journal_from_doi(doi: str) -> Optional[str]:
    """Infer journal name from DOI prefix (V20.1, ported from build_database.py)."""
    if not doi:
        return None
    doi_lower = doi.lower()
    # Common DOI prefixes for major journals
    doi_journal_map = {
        "10.1038/s41586": "Nature",
        "10.1038/s41591": "Nature Medicine",
        "10.1038/s41587": "Nature Biotechnology",
        "10.1038/s41467": "Nature Communications",
        "10.1016/j.cell": "Cell",
        "10.1016/j.molcel": "Molecular Cell",
        "10.1016/j.ccell": "Cancer Cell",
        "10.1126/science": "Science",
        "10.1126/sciadv": "Science Advances",
        "10.1172/jci": "Journal of Clinical Investigation",
        "10.1084/jem": "Journal of Experimental Medicine",
    }
    for prefix, journal in doi_journal_map.items():
        if doi_lower.startswith(prefix):
            return journal
    return None


class ParserOrchestrator:
    """Orchestrates PDF parsing - V3: Docling primary + GROBID enrichment"""

    def __init__(self):
        self.docling = DoclingParser()
        self.grobid = None

        # Try to initialize GROBID (optional)
        if GROBID_AVAILABLE:
            try:
                self.grobid = GrobidParser()
                if not self.grobid.is_alive():
                    print("ℹ️  GROBID server not running; metadata/citations will rely on Docling.")
                    print("   To enable: docker run -d --rm -p 8070:8070 grobid/grobid:0.9.1-full")
                    self.grobid = None
                else:
                    print("✅ GROBID active: will enrich metadata + references")
            except Exception as e:
                print(f"⚠️  GROBID init failed: {str(e)[:80]}")
                self.grobid = None
        else:
            print("ℹ️  GROBID not available; using Docling only.")

        print("✅ Parser Orchestrator initialized (V3: Docling + optional GROBID)")

    def parse_paper(self, pdf_path: str, paper_id: str = None) -> Dict[str, Any]:
        """
        Parse a complete paper using Docling + optional GROBID enrichment.

        Args:
            pdf_path: Path to PDF file
            paper_id: Optional paper ID, auto-generated if not provided

        Returns:
            Parsed result ready for database insertion
        """
        if not paper_id:
            paper_id = self._generate_paper_id(pdf_path)

        print("=" * 60)
        print(f"Starting parse pipeline for: {os.path.basename(pdf_path)}")
        print(f"Paper ID: {paper_id}")
        print("=" * 60)

        # Step 1: Run Docling primary parser
        print("\n📝 Step 1: Running Docling parser...")
        result = self.docling.parse(pdf_path, paper_id)

        # Step 2: GROBID enrichment (metadata + citations)
        if self.grobid is not None:
            print("\n📚 Step 2: GROBID enrichment (metadata + citations)...")
            try:
                gres = self.grobid.parse(pdf_path, paper_id)
                if 'error' not in gres:
                    self._merge_grobid_result(result, gres, paper_id)
                else:
                    print(f"   ⚠️  GROBID parse error: {gres.get('error')}")
            except Exception as e:
                print(f"   ⚠️  GROBID enrichment failed: {str(e)[:100]}")
                print("   Continuing with Docling-only result.")
        else:
            print("\n⏭️  Step 2: GROBID skipped (service not available)")

        # Step 3: Post-processing (journal-aware optimization)
        print("\n🔄 Step 3: Journal-aware post-processing...")
        try:
            from .journal_optimizer import optimize_for_journal
            result = optimize_for_journal(result)
        except Exception as e:
            print(f"   ⚠️  Journal optimization skipped: {str(e)[:80]}")

        print("\n" + "=" * 60)
        print("✅ Parse pipeline complete!")
        print(f"  - Paragraphs: {len(result['paragraphs'])}")
        print(f"  - Figures: {len(result['figures'])}")
        print(f"  - Citations: {len(result.get('citations', []))}")
        print(f"  - Tables: {len(result.get('tables', []))}")
        print("=" * 60)

        return result

    def _merge_grobid_result(self, result: Dict[str, Any], gres: Dict[str, Any], paper_id: str):
        """
        Merge GROBID enrichment into Docling result.
        - Metadata: GROBID wins (title must pass sanity check)
        - Citations: GROBID replaces Docling (GROBID is much better at this)
        - Add citation_id and paper_id to each citation for db_writer
        """
        grobid_meta = gres.get('metadata') or {}
        grobid_citations = gres.get('citations') or []

        # --- Merge metadata ---
        current_meta = result.get('metadata', {})

        # Title: accept GROBID only if it passes sanity check
        g_title = (grobid_meta.get('title') or '').strip()
        if g_title:
            suspicious, reason = is_grobid_title_suspicious(g_title)
            if suspicious:
                print(f"   ⚠️  GROBID title rejected ({reason}): {g_title[:50]!r}")
                print(f"      -> keeping Docling title")
            else:
                current_meta['title'] = g_title
                print(f"   ✅ Title from GROBID: {g_title[:50]}")

        # Authors: GROBID wins
        if grobid_meta.get('authors'):
            current_meta['authors'] = grobid_meta['authors']

        # Journal: GROBID wins, fallback to DOI inference
        if grobid_meta.get('journal'):
            current_meta['journal'] = grobid_meta['journal']
        elif not current_meta.get('journal') and grobid_meta.get('doi'):
            inferred = journal_from_doi(grobid_meta['doi'])
            if inferred:
                current_meta['journal'] = inferred
                print(f"   ✅ Journal inferred from DOI: {inferred}")

        # DOI: GROBID wins
        if grobid_meta.get('doi'):
            current_meta['doi'] = grobid_meta['doi']

        # Year: GROBID wins
        if grobid_meta.get('year'):
            current_meta['year'] = grobid_meta['year']

        # Abstract: GROBID wins (if available)
        if grobid_meta.get('abstract'):
            current_meta['abstract'] = grobid_meta['abstract']

        result['metadata'] = current_meta

        # --- Merge citations ---
        if grobid_citations:
            # Add citation_id and paper_id to each citation (db_writer expects these)
            enriched_citations = []
            for i, ref in enumerate(grobid_citations, 1):
                enriched = dict(ref)
                enriched['citation_id'] = f"cite_{paper_id}_{i:04d}"
                enriched['paper_id'] = paper_id
                enriched_citations.append(enriched)
            result['citations'] = enriched_citations
            print(f"   ✅ Citations from GROBID: {len(enriched_citations)} structured references")
        else:
            print(f"   ℹ️  GROBID returned no citations; keeping Docling citations")

    def _generate_paper_id(self, pdf_path: str) -> str:
        """Generate a unique paper ID from file hash"""
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:12]
        filename = os.path.basename(pdf_path).replace(".pdf", "")
        # Clean filename for ID
        clean_name = "".join(c if c.isalnum() else "_" for c in filename)[:50]
        return f"paper_{clean_name}_{file_hash}"
