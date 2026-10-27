"""
Grobid Parser for Sci-Pal
V2.0 - Full TEI XML parsing
- Extracts metadata (title, authors, DOI, journal, year)
- Extracts structured references (authors, title, journal, year, DOI)
- Extracts section hierarchy
- Complements Docling (which handles figures/tables/layout)
"""
import os
import re
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import requests


# Grobid server config (SCIPAL_GROBID_URL wins; GROBID_URL kept for compatibility)
GROBID_URL = os.environ.get("SCIPAL_GROBID_URL") or os.environ.get(
    "GROBID_URL", "http://localhost:8070"
)

# XML namespaces used in TEI
TEI_NS = {
    'tei': 'http://www.tei-c.org/ns/1.0',
}

# DOI regex (handles dx.doi.org / doi: / bare 10.xxxx prefixes, spaced-out text)
_DOI_RE = re.compile(r'10\.\d{4,9}/[^\s;,\]\)\"<>]+', re.IGNORECASE)


def find_doi_in_text(text: Optional[str]) -> Optional[str]:
    """Extract the first plausible DOI from a free-text string."""
    if not text:
        return None

    def _clean(m: str) -> str:
        return m.rstrip('.,;:').lower()

    # 1) Normal text: a DOI contains no spaces, regex stops at whitespace,
    #    so trailing words like "for details" are naturally excluded.
    m = _DOI_RE.search(text)
    if m:
        return _clean(m.group(0))
    # 2) Fallback for spaced-out DOIs ("1 0 . 1 0 1 6 / ..."): strip spaces.
    compact = re.sub(r'\s+', '', text)
    m = _DOI_RE.search(compact)
    if m:
        return _clean(m.group(0))
    return None


class GrobidParser:
    """Client for Grobid PDF parsing service"""
    
    def __init__(self, base_url: str = GROBID_URL):
        self.name = "grobid"
        self.base_url = base_url.rstrip('/')
        self.api_url = f"{self.base_url}/api"
        self._available = None
    
    def get_parser_name(self) -> str:
        return self.name
    
    def is_alive(self) -> bool:
        """Check if Grobid server is running"""
        if self._available is not None:
            return self._available
        try:
            r = requests.get(f"{self.api_url}/isalive", timeout=5)
            self._available = r.status_code == 200 and r.text.strip() == "true"
            if self._available:
                print("✅ Grobid server is available")
            else:
                print("⚠️  Grobid server not responding correctly")
        except Exception as e:
            self._available = False
            print(f"⚠️  Grobid not available: {e}")
            print("   Start it with:")
            print("   docker run --rm --gpus all --init --ulimit core=0 -p 8070:8070 grobid/grobid:0.9.1-full")
        return self._available
    
    def process_pdf(self, pdf_path: str, timeout: int = 120) -> Optional[str]:
        """Send PDF to Grobid and return TEI XML string"""
        url = f"{self.api_url}/processFulltextDocument"
        
        with open(pdf_path, 'rb') as f:
            files = {'input': (Path(pdf_path).name, f, 'application/pdf')}
            data = {
                # Consolidation calls external CrossRef API per citation -> very slow
                # behind a proxy. Keep OFF: local models already extract DOI/metadata.
                'consolidateHeader': '0',
                'consolidateCitations': '0',
                'includeRawCitations': '1',
                'includeRawAffiliations': '1',
                'teiCoordinates': ['ref', 'figure', 'table', 'head'],
            }
            r = requests.post(url, files=files, data=data, timeout=timeout)
        
        if r.status_code == 200:
            return r.text
        else:
            print(f"    ⚠️  Grobid error {r.status_code}: {r.text[:100]}")
            return None
    
    def parse_header(self, tei_xml: str) -> dict:
        """Extract paper metadata from TEI XML"""
        result = {
            'title': None,
            'authors': None,
            'journal': None,
            'doi': None,
            'year': None,
            'abstract': None,
        }
        
        try:
            root = ET.fromstring(tei_xml)
        except ET.ParseError:
            return result
        
        # Title
        title_elem = root.find('.//tei:fileDesc/tei:titleStmt/tei:title', TEI_NS)
        if title_elem is not None and title_elem.text:
            result['title'] = title_elem.text.strip()
        
        # Authors (from analytic/biblStruct in sourceDesc)
        authors = []
        for author in root.findall(
            './/tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:analytic/tei:author',
            TEI_NS
        ):
            pers_name = author.find('.//tei:persName', TEI_NS)
            if pers_name is not None:
                forename = pers_name.find('tei:forename', TEI_NS)
                surname = pers_name.find('tei:surname', TEI_NS)
                if forename is not None and surname is not None:
                    authors.append(f"{forename.text} {surname.text}")
                elif surname is not None:
                    authors.append(surname.text)
        if authors:
            result['authors'] = '; '.join(authors[:15])
        
        # Journal: Grobid marks it <title level="j"> inside <monogr>.
        # Iterate all monogr titles and prefer level="j", else first non-empty.
        journal = None
        for monogr in root.findall(
            './/tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:monogr',
            TEI_NS
        ):
            level_j = None
            first_nonempty = None
            for t in monogr.findall('tei:title', TEI_NS):
                txt = ''.join(t.itertext()).strip() if t is not None else ''
                if not txt:
                    continue
                if t.get('level') == 'j':
                    level_j = txt
                    break
                if first_nonempty is None:
                    first_nonempty = txt
            journal = level_j or first_nonempty
            if journal:
                break
        if journal:
            result['journal'] = journal
        
        # DOI
        for idno in root.findall(
            './/tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:idno',
            TEI_NS
        ):
            if idno.get('type') == 'DOI' and idno.text:
                result['doi'] = idno.text.strip()
                break
        
        # Year
        date_elem = root.find(
            './/tei:fileDesc/tei:sourceDesc/tei:biblStruct/tei:monogr/tei:imprint/tei:date',
            TEI_NS
        )
        if date_elem is not None and date_elem.get('when'):
            year_str = date_elem.get('when')[:4]
            if year_str.isdigit():
                result['year'] = int(year_str)
        
        # Abstract
        abstract_elem = root.find('.//tei:profileDesc/tei:abstract', TEI_NS)
        if abstract_elem is not None:
            abstract_text = ''.join(abstract_elem.itertext()).strip()
            if abstract_text:
                result['abstract'] = abstract_text[:2000]
        
        return result
    
    def parse_references(self, tei_xml: str) -> list:
        """Extract structured references from TEI XML"""
        references = []
        
        try:
            root = ET.fromstring(tei_xml)
        except ET.ParseError:
            return references
        
        bibl_structs = root.findall('.//tei:listBibl/tei:biblStruct', TEI_NS)
        
        for i, bibl in enumerate(bibl_structs):
            ref = {
                'ref_number': str(i + 1),
                'raw_text': None,
                'doi': None,
                'title': None,
                'authors': None,
                'journal': None,
                'year': None,
            }
            
            # Raw text
            note = bibl.find('.//tei:note[@type="raw_reference"]', TEI_NS)
            if note is not None and note.text:
                ref['raw_text'] = note.text.strip()
            
            # DOI (structured idno first)
            for idno in bibl.findall('.//tei:idno', TEI_NS):
                if idno.get('type') == 'DOI' and idno.text:
                    ref['doi'] = idno.text.strip()
                    break
            # Fallback: regex the DOI out of the raw reference text when it
            # is printed in the bibliography (consolidation is off, so Grobid
            # does not look missing DOIs up online).
            if not ref['doi'] and ref['raw_text']:
                ref['doi'] = find_doi_in_text(ref['raw_text'])
            
            # Title
            title_elem = bibl.find('.//tei:analytic/tei:title', TEI_NS)
            if title_elem is not None and title_elem.text:
                ref['title'] = title_elem.text.strip()
            
            # Authors
            authors = []
            for author in bibl.findall('.//tei:analytic/tei:author', TEI_NS):
                pers_name = author.find('.//tei:persName', TEI_NS)
                if pers_name is not None:
                    forename = pers_name.find('tei:forename', TEI_NS)
                    surname = pers_name.find('tei:surname', TEI_NS)
                    if forename is not None and surname is not None:
                        authors.append(f"{forename.text} {surname.text}")
                    elif surname is not None:
                        authors.append(surname.text)
            if authors:
                ref['authors'] = '; '.join(authors)
            
            # Journal (prefer level="j")
            for jt in bibl.findall('.//tei:monogr/tei:title', TEI_NS):
                txt = ''.join(jt.itertext()).strip()
                if txt and (jt.get('level') == 'j' or not ref['journal']):
                    ref['journal'] = txt
                    if jt.get('level') == 'j':
                        break
            
            # Year
            date_elem = bibl.find('.//tei:monogr/tei:imprint/tei:date', TEI_NS)
            if date_elem is not None and date_elem.get('when'):
                year_str = date_elem.get('when')[:4]
                if year_str.isdigit():
                    ref['year'] = int(year_str)
            
            # Fallback: build raw_text from structured data
            if not ref['raw_text']:
                parts = []
                if ref['authors']:
                    parts.append(ref['authors'])
                if ref['title']:
                    parts.append(ref['title'])
                if ref['journal']:
                    parts.append(ref['journal'])
                if ref['year']:
                    parts.append(str(ref['year']))
                if parts:
                    ref['raw_text'] = '. '.join(parts)
            
            references.append(ref)
        
        return references
    
    def parse_intext_citations(self, tei_xml: str) -> list:
        """
        Extract in-text citation links from TEI XML.
        GROBID already links <ref type="bibr" target="#b6"> to <biblStruct xml:id="b6">.
        Returns list of {target_id, page, bbox, context}
        """
        intext_citations = []

        try:
            root = ET.fromstring(tei_xml)
        except ET.ParseError:
            return intext_citations

        # Build map: biblStruct xml:id -> index (ref_number)
        bibl_id_map = {}
        bibl_structs = root.findall('.//tei:listBibl/tei:biblStruct', TEI_NS)
        for i, bibl in enumerate(bibl_structs):
            xml_id = bibl.get('{http://www.w3.org/XML/1998/namespace}id')
            if xml_id:
                bibl_id_map[xml_id] = str(i + 1)  # ref_number starts from 1

        # Find all in-text citations
        body = root.find('.//tei:text/tei:body', TEI_NS)
        if body is None:
            return intext_citations

        for ref_elem in body.findall('.//tei:ref', TEI_NS):
            ref_type = ref_elem.get('type')
            if ref_type != 'bibr':
                continue

            target = ref_elem.get('target', '')
            if target.startswith('#'):
                target_id = target[1:]  # Remove '#'
            else:
                target_id = target

            # Get surrounding text (context)
            context = ''.join(ref_elem.itertext()).strip()

            # Get coordinates if available
            coords = ref_elem.find('.//tei:coords', TEI_NS)
            page = None
            bbox = None
            if coords is not None:
                page = coords.get('page')
                bbox_str = coords.get('points', '')
                if bbox_str:
                    bbox = bbox_str

            intext_citations.append({
                'target_id': target_id,
                'ref_number': bibl_id_map.get(target_id),
                'context': context[:200],
                'page': page,
                'bbox': bbox,
            })

        return intext_citations

    def parse_sections(self, tei_xml: str) -> list:
        """Extract section hierarchy from TEI XML"""
        sections = []
        
        try:
            root = ET.fromstring(tei_xml)
        except ET.ParseError:
            return sections
        
        body = root.find('.//tei:text/tei:body', TEI_NS)
        if body is None:
            return sections
        
        def walk_div(div_elem, level=1):
            head = div_elem.find('tei:head', TEI_NS)
            title = head.text.strip() if head is not None and head.text else None
            
            if title:
                sections.append({'level': level, 'title': title})
            
            for child in div_elem.findall('tei:div', TEI_NS):
                walk_div(child, level + 1)
        
        for div in body.findall('tei:div', TEI_NS):
            walk_div(div, 1)
        
        return sections
    
    def parse(self, pdf_path: str, paper_id: str = "") -> dict:
        """Full parse: metadata + references + sections (compatible with BaseParser API)"""
        if not self.is_alive():
            return {"citations": [], "metadata": {}, "sections": [], "error": "GROBID not available"}
        
        print(f"📚 Parsing with Grobid: {os.path.basename(pdf_path)}")
        
        tei_xml = self.process_pdf(pdf_path)
        if not tei_xml:
            return {"citations": [], "metadata": {}, "sections": [], "error": "parse failed"}
        
        header = self.parse_header(tei_xml)
        references = self.parse_references(tei_xml)
        sections = self.parse_sections(tei_xml)
        intext_citations = self.parse_intext_citations(tei_xml)

        # Format citations to match our DB schema
        citations = []
        for ref in references:
            citations.append({
                "ref_number": ref['ref_number'],
                "raw_text": ref['raw_text'],
                "doi": ref['doi'],
                "title": ref['title'],
                "authors": ref['authors'],
                "journal": ref['journal'],
                "year": ref['year'],
            })

        print(f"  ✅ {len(citations)} citations, title: {header['title'][:40] if header['title'] else 'N/A'}")
        print(f"  🔗 GROBID: {len(intext_citations)} in-text citation links")

        return {
            "metadata": header,
            "citations": citations,
            "sections": sections,
            "intext_citations": intext_citations,
        }


# ============================================================
# Standalone test
# ============================================================
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent
    pdf_dir = project_root / "documents"
    
    parser = GrobidParser()
    
    print("=" * 70)
    print("🔧 Grobid Parser Test (TEI XML)")
    print("=" * 70)
    
    if not parser.is_alive():
        exit(1)
    
    # Test on first 3 PDFs
    pdfs = sorted(pdf_dir.glob("*.pdf"))[:3]
    
    import time as _time
    for pdf in pdfs:
        print(f"\n{'=' * 70}")
        print(f"📄 {pdf.name}")
        print("=" * 70)
        
        t0 = _time.time()
        try:
            result = parser.parse(str(pdf))
        except Exception as e:
            print(f"  ❌ Parse failed: {type(e).__name__}: {str(e)[:120]}")
            continue
        elapsed = _time.time() - t0
        print(f"  ⏱️  Parsed in {elapsed:.1f}s")
        
        if 'error' in result:
            print(f"  ❌ {result['error']}")
            continue
        
        header = result['metadata']
        print(f"\n📋 Header:")
        print(f"  Title:   {header['title']}")
        print(f"  Authors: {(header['authors'] or 'N/A')[:80]}")
        print(f"  Journal: {header['journal']}")
        print(f"  DOI:     {header['doi']}")
        print(f"  Year:    {header['year']}")
        
        refs = result['citations']
        n_doi = sum(1 for r in refs if r['doi'])
        print(f"\n📚 References: {len(refs)} total, {n_doi} with DOI")
        for ref in refs[:3]:
            print(f"  [{ref['ref_number']}] DOI: {ref['doi'] or 'N/A'}")
            print(f"      Title: {(ref['title'] or 'N/A')[:60]}")
            print(f"      Journal: {ref['journal'] or 'N/A'}")
            print(f"      Year: {ref['year'] or 'N/A'}")
        if len(refs) > 3:
            print(f"  ... and {len(refs) - 3} more")
        
        sections = result['sections']
        print(f"\n📂 Sections: {len(sections)} total")
        for sec in sections[:10]:
            indent = "  " * sec['level']
            print(f"{indent}L{sec['level']}: {sec['title'][:60]}")
        if len(sections) > 10:
            print(f"  ... and {len(sections) - 10} more")
