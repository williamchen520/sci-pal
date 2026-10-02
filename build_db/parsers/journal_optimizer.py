"""
Journal-Aware PDF Optimizer
V25.16: Targeted optimization for Nature, Science, Cell (and their sub-journals)

Detects journal family from metadata/DOI, then applies:
- Journal-specific section heading recognition
- Volume/issue/pages extraction
- Section type normalization
- Two-column layout hints

Supported families:
- Nature (Nature, Nature Medicine, Nature Biotechnology, Nature Communications, ...)
- Science (Science, Science Advances, Science Robotics, ...)
- Cell (Cell, Molecular Cell, Cancer Cell, Cell Reports, ...)
- Other (generic optimization)
"""
import re
from typing import Dict, List, Any, Optional, Tuple


# ============================================================
# Journal family detection
# ============================================================

# DOI prefix -> journal family mapping
DOI_PREFIX_MAP = {
    # Nature family
    "10.1038/s41586": "nature",
    "10.1038/s41591": "nature",
    "10.1038/s41587": "nature",
    "10.1038/s41467": "nature",
    "10.1038/s41590": "nature",
    "10.1038/s41593": "nature",
    "10.1038/s41594": "nature",
    "10.1038/s41556": "nature",
    "10.1038/s41564": "nature",
    "10.1038/s41565": "nature",
    "10.1038/s41566": "nature",
    "10.1038/s41567": "nature",
    "10.1038/s41568": "nature",
    "10.1038/s41569": "nature",
    "10.1038/s41570": "nature",
    "10.1038/s41571": "nature",
    "10.1038/s41572": "nature",
    "10.1038/s41573": "nature",
    "10.1038/s41574": "nature",
    "10.1038/s41575": "nature",
    "10.1038/s41576": "nature",
    "10.1038/s41577": "nature",
    "10.1038/s41578": "nature",
    "10.1038/s41579": "nature",
    "10.1038/s41580": "nature",
    "10.1038/s41581": "nature",
    "10.1038/s41582": "nature",
    "10.1038/s41583": "nature",
    "10.1038/s41584": "nature",
    "10.1038/s41585": "nature",
    "10.1038/nature": "nature",
    "10.1038/nm": "nature",
    "10.1038/nbt": "nature",
    "10.1038/ncomms": "nature",
    "10.1038/ni": "nature",
    "10.1038/ne": "nature",
    "10.1038/nsmb": "nature",
    "10.1038/nchembio": "nature",
    "10.1038/nmat": "nature",
    "10.1038/nphys": "nature",
    "10.1038/nnano": "nature",
    "10.1038/nphoton": "nature",
    "10.1038/nmeth": "nature",
    "10.1038/nprot": "nature",
    "10.1038/nrg": "nature",
    "10.1038/nri": "nature",
    "10.1038/nrc": "nature",
    "10.1038/nrd": "nature",
    "10.1038/nrm": "nature",
    "10.1038/nrmicro": "nature",
    "10.1038/nrcardio": "nature",
    "10.1038/nrneurol": "nature",
    "10.1038/nrendo": "nature",
    "10.1038/nrclinonc": "nature",
    # Science family
    "10.1126/science": "science",
    "10.1126/sciadv": "science",
    "10.1126/scirobotics": "science",
    "10.1126/scitranslmed": "science",
    "10.1126/scisignal": "science",
    "10.1126/scimed": "science",
    "10.1126/sciimmunol": "science",
    # Cell family (Elsevier)
    "10.1016/j.cell": "cell",
    "10.1016/j.molcel": "cell",
    "10.1016/j.ccell": "cell",
    "10.1016/j.celrep": "cell",
    "10.1016/j.stem": "cell",
    "10.1016/j.immuni": "cell",
    "10.1016/j.str": "cell",
    "10.1016/j.chembiol": "cell",
    "10.1016/j.celrepmed": "cell",
    "10.1016/j.xcrm": "cell",
    "10.1016/j.xgen": "cell",
    "10.1016/j.xinn": "cell",
    # JCI (often grouped with top journals)
    "10.1172/jci": "other",
    "10.1084/jem": "other",
}

# Journal name keywords -> family
JOURNAL_NAME_MAP = {
    "nature": "nature",
    "science": "science",
    "cell": "cell",
    "molecular cell": "cell",
    "cancer cell": "cell",
    "cell reports": "cell",
    "cell stem cell": "cell",
    "immunity": "cell",
    "nature medicine": "nature",
    "nature biotechnology": "nature",
    "nature communications": "nature",
    "nature immunology": "nature",
    "science advances": "science",
    "science robotics": "science",
}


def detect_journal_family(metadata: Dict[str, Any]) -> Tuple[str, str]:
    """
    Detect journal family from metadata.
    Returns (family, detection_method)
    family: 'nature' | 'science' | 'cell' | 'other'
    """
    # 1. Try DOI prefix
    doi = (metadata.get('doi') or '').strip().lower()
    if doi:
        for prefix, family in DOI_PREFIX_MAP.items():
            if doi.startswith(prefix):
                return family, f"doi:{prefix}"

    # 2. Try journal name
    journal = (metadata.get('journal') or '').strip().lower()
    if journal:
        for name_key, family in JOURNAL_NAME_MAP.items():
            if name_key in journal:
                return family, f"journal:{journal}"

    # 3. Try title patterns (less reliable)
    title = (metadata.get('title') or '').lower()
    if title:
        if 'nature' in title and 'cell' not in title:
            return 'nature', 'title:contains nature'
        if 'science' in title and 'cell' not in title and 'nature' not in title:
            return 'science', 'title:contains science'

    return 'other', 'not detected'


# ============================================================
# Journal-specific section heading patterns
# ============================================================

# Cell (Cell Press) specific headings
# Official source: Cell Press STAR Methods guide (cell.com)
# Key facts:
# - First section is "Summary" (with heading) -> abstract
# - Methods is "STAR Methods" with 4 mandatory sub-headings (all caps in PDF):
#   1. RESOURCE AVAILABILITY (Lead Contact / Materials Availability / Data and Code Availability)
#   2. EXPERIMENTAL MODEL AND SUBJECT DETAILS
#   3. METHOD DETAILS
#   4. QUANTIFICATION AND STATISTICAL ANALYSIS
# - Plus Key Resources Table
# - STAR Methods appears AFTER figure legends
CELL_HEADINGS = {
    'summary': 'abstract',
    'abstract': 'abstract',
    'introduction': 'introduction',
    'results': 'results',
    'discussion': 'discussion',
    'star methods': 'methods',
    'star\u25cf methods': 'methods',
    'methods': 'methods',
    'materials and methods': 'methods',
    'experimental procedures': 'methods',
    # STAR Methods sub-headings (official)
    'resource availability': 'methods',
    'lead contact': 'methods',
    'materials availability': 'methods',
    'data and code availability': 'methods',
    'data availability': 'methods',
    'code availability': 'methods',
    'experimental model and subject details': 'methods',
    'experimental model': 'methods',
    'method details': 'methods',
    'quantification and statistical analysis': 'methods',
    'quantification': 'methods',
    'statistical analysis': 'methods',
    'key resources table': 'methods',
    'key resources': 'methods',
    'references': 'references',
    'references and notes': 'references',
    'acknowledgments': 'other',
    'acknowledgements': 'other',
    'author contributions': 'other',
    'declaration of interests': 'other',
    'figure legends': 'figure_caption',
    'supplemental information': 'other',
    'supplementary information': 'other',
    'supplemental experimental procedures': 'methods',
}

# Nature specific headings
# Official source: Nature Formatting Guide (nature.com/nature/for-authors/formatting-guide)
# Key facts:
# - First section is "bold first paragraph" (no heading), ~200 words -> abstract
# - Methods comes AFTER figure legends, called "Methods" (online-only, not in print)
# - Two reference sets: "main references" (in body) and "methods references" (after Methods)
# - In-text citations are superscript, not brackets
# - Full order: bold first paragraph -> main text -> main references -> tables ->
#   figure legends -> methods -> methods references -> acknowledgements -> ...
NATURE_HEADINGS = {
    'abstract': 'abstract',
    # NOTE: Nature does NOT use "Summary" as a heading; first para is bold & untitled.
    # Handled specially in optimize_for_journal() (para_index==1, empty title -> abstract).
    'introduction': 'introduction',
    'background': 'introduction',
    'results': 'results',
    'discussion': 'discussion',
    'methods': 'methods',
    'materials and methods': 'methods',
    'online-only methods': 'methods',
    'methods summary': 'methods',
    'main references': 'references',
    'references': 'references',
    'methods references': 'references',
    'acknowledgements': 'other',
    'acknowledgments': 'other',
    'funding': 'other',
    'funding statement': 'other',
    'author contributions': 'other',
    'competing interests': 'other',
    'competing interest declaration': 'other',
    'competing financial interests': 'other',
    'additional information': 'other',
    'extended data': 'figure_caption',
    'extended data figure': 'figure_caption',
    'extended data table': 'figure_caption',
    'figure legends': 'figure_caption',
    'supplementary information': 'other',
    'supplementary methods': 'methods',
    'data availability': 'other',
    'code availability': 'other',
}

# Science specific headings
# Official source: Science Information for Authors (science.org)
# Key facts:
# - "Materials and Methods should be included in supplementary materials"
#   -> Methods is usually NOT in the main text; it's in supplementary materials
# - Main text <=3000 words, divided into sections with brief subheadings
# - In-text citations use [1] bracket style
# - For online extended format, Methods runs after main text
SCIENCE_HEADINGS = {
    'abstract': 'abstract',
    'summary': 'abstract',
    'introduction': 'introduction',
    'rationale': 'introduction',
    'background': 'introduction',
    'results': 'results',
    'findings': 'results',
    'discussion': 'discussion',
    'conclusion': 'discussion',
    'materials and methods': 'methods',
    'methods': 'methods',
    'materials and methods summary': 'methods',
    'references': 'references',
    'references and notes': 'references',
    'acknowledgments': 'other',
    'acknowledgements': 'other',
    'supplementary materials': 'other',
    'supplementary online material': 'other',
    'som text': 'other',
    'supporting online material': 'other',
}

# Generic fallback (for 'other' family)
GENERIC_HEADINGS = {
    'abstract': 'abstract',
    'summary': 'abstract',
    'introduction': 'introduction',
    'background': 'introduction',
    'methods': 'methods',
    'materials and methods': 'methods',
    'experimental procedures': 'methods',
    'results': 'results',
    'discussion': 'discussion',
    'conclusion': 'discussion',
    'conclusions': 'discussion',
    'references': 'references',
    'bibliography': 'references',
}

FAMILY_HEADING_MAP = {
    'cell': CELL_HEADINGS,
    'nature': NATURE_HEADINGS,
    'science': SCIENCE_HEADINGS,
    'other': GENERIC_HEADINGS,
}


def classify_section_journal_aware(section_title: str, family: str) -> str:
    """
    Classify section type using journal-specific heading patterns.
    More accurate than generic keyword matching for top journals.
    """
    if not section_title:
        return 'body'

    title_lower = section_title.strip().lower()
    heading_map = FAMILY_HEADING_MAP.get(family, GENERIC_HEADINGS)

    # Exact match first
    if title_lower in heading_map:
        return heading_map[title_lower]

    # Partial match (heading may have numbering like "1. Introduction" or "Results and Discussion")
    for heading, section_type in heading_map.items():
        if heading in title_lower:
            return section_type

    # Special: "Results and Discussion" -> results (primary)
    if 'result' in title_lower and 'discussion' in title_lower:
        return 'results'

    # Special: figure/table captions
    if any(kw in title_lower for kw in ['figure ', 'fig. ', 'table ', 'figure legend', 'fig legend']):
        return 'figure_caption'

    return 'body'


# ============================================================
# Volume/Issue/Pages extraction
# ============================================================

def extract_volume_issue_pages(metadata: Dict[str, Any], family: str) -> Dict[str, str]:
    """
    Extract volume, issue, pages from metadata or DOI.
    Returns dict with 'volume', 'issue', 'pages' keys (empty string if not found).
    """
    result = {'volume': '', 'issue': '', 'pages': ''}

    # 1. Try direct metadata fields (GROBID may provide these in future)
    for key in ['volume', 'issue', 'pages']:
        val = metadata.get(key)
        if val:
            result[key] = str(val).strip()

    # 2. Try to extract from journal field (e.g., "Nature 580, 123-145 (2020)")
    journal = (metadata.get('journal') or '').strip()
    if journal and not result['volume']:
        # Pattern: "Journal Name Volume, Pages (Year)" or "Journal Name Volume(Issue):Pages"
        vol_match = re.search(r'\b(\d{1,4})\s*[,(\[]', journal)
        if vol_match:
            result['volume'] = vol_match.group(1)
        pages_match = re.search(r'(\d{1,5})\s*[-–]\s*(\d{1,5})', journal)
        if pages_match:
            result['pages'] = f"{pages_match.group(1)}-{pages_match.group(2)}"

    # 3. Try DOI-based extraction (limited, DOI doesn't usually contain volume/pages)
    #    But for some publishers we can infer from DOI structure
    doi = (metadata.get('doi') or '').strip()
    if doi and family == 'nature':
        # Nature DOIs sometimes contain article number, not volume/pages
        pass

    return result


# ============================================================
# Metadata field extraction (abstract, affiliations, funding)
# ============================================================

# Section title patterns for metadata extraction
ABSTRACT_PATTERNS = [
    r'^abstract$', r'^summary$', r'^a\s*b\s*s\s*t\s*r\s*a\s*c\s*t$',
    r'^graphical\s+abstract$', r'^highlights$',
]
AFFILIATION_PATTERNS = [
    r'^affiliations?$', r'^affiliation\s+list$', r'^author\s+affiliations?$',
    r'^institutions?$', r'^addresses?$',
]
FUNDING_PATTERNS = [
    r'^funding$', r'^acknowledg?ements?$', r'^financial\s+support$',
    r'^grant\s+information$', r'^funding\s+statement$',
    r'^data\s+availability$', r'^code\s+availability$',
]


def _match_section_title(title: str, patterns: List[str]) -> bool:
    """Check if a section title matches any of the patterns (case-insensitive)."""
    if not title:
        return False
    title_clean = title.strip().lower()
    for pat in patterns:
        if re.match(pat, title_clean, re.IGNORECASE):
            return True
    return False


def extract_metadata_fields(parsed_result: Dict[str, Any], family: str) -> Dict[str, str]:
    """
    V25.18: Extract abstract, affiliations, funding from parsed paragraphs.

    Strategy:
    1. Scan paragraphs for section titles matching abstract/affiliation/funding patterns
    2. Collect text from subsequent body paragraphs until next section heading
    3. For Nature: the first "bold summary paragraph" (already re-classified as abstract) is the abstract
    4. Deduplicate and clean

    Returns dict with 'abstract', 'affiliations', 'funding' keys.
    """
    result = {'abstract': '', 'affiliations': '', 'funding': ''}
    paragraphs = parsed_result.get('paragraphs', [])
    if not paragraphs:
        return result

    # Helper: collect text from paragraphs starting at index until next section heading
    def collect_section_text(start_idx: int, max_paras: int = 10) -> str:
        texts = []
        for i in range(start_idx, min(start_idx + max_paras, len(paragraphs))):
            para = paragraphs[i]
            # Stop if we hit another section heading (non-body section_type)
            sec_type = para.get('section_type', 'body')
            sec_title = para.get('section_title', '')
            if i > start_idx and sec_type != 'body' and sec_title:
                break
            text = para.get('text_content') or para.get('text', '')
            if text and len(text.strip()) > 10:
                texts.append(text.strip())
        return ' '.join(texts)

    # Scan paragraphs for section headings
    for idx, para in enumerate(paragraphs):
        sec_title = para.get('section_title', '')
        sec_type = para.get('section_type', 'body')

        # Abstract detection
        if not result['abstract']:
            # Direct section_type = abstract (including Nature's bold first paragraph)
            if sec_type == 'abstract':
                text = para.get('text_content') or para.get('text', '')
                if text and len(text.strip()) > 20:
                    result['abstract'] = text.strip()
                # Also collect following paragraphs if they're part of abstract
                follow_text = collect_section_text(idx + 1, max_paras=3)
                if follow_text:
                    result['abstract'] = (result['abstract'] + ' ' + follow_text).strip()
            # Section title matching
            elif _match_section_title(sec_title, ABSTRACT_PATTERNS):
                text = para.get('text_content') or para.get('text', '')
                if text and len(text.strip()) > 20:
                    result['abstract'] = text.strip()
                follow_text = collect_section_text(idx + 1, max_paras=5)
                if follow_text:
                    result['abstract'] = (result['abstract'] + ' ' + follow_text).strip()

        # Affiliations detection
        if not result['affiliations'] and _match_section_title(sec_title, AFFILIATION_PATTERNS):
            text = para.get('text_content') or para.get('text', '')
            if text and len(text.strip()) > 10:
                result['affiliations'] = text.strip()
            follow_text = collect_section_text(idx + 1, max_paras=10)
            if follow_text:
                result['affiliations'] = (result['affiliations'] + ' ' + follow_text).strip()

        # Funding detection
        if not result['funding'] and _match_section_title(sec_title, FUNDING_PATTERNS):
            text = para.get('text_content') or para.get('text', '')
            if text and len(text.strip()) > 10:
                result['funding'] = text.strip()
            follow_text = collect_section_text(idx + 1, max_paras=10)
            if follow_text:
                result['funding'] = (result['funding'] + ' ' + follow_text).strip()

    # ── Fallback: 无明确 Abstract 标题时，找 Introduction 前的最后一个正文段 ──
    if not result['abstract']:
        # 找到第一个 Introduction 章节的位置
        intro_idx = -1
        for idx, para in enumerate(paragraphs):
            sec_title = (para.get('section_title') or '').strip().lower()
            # 匹配 "Introduction"、"1. Introduction"、"INTRODUCTION"、"1 Introduction" 等
            if re.match(r'^(\d+\.?\s*)?introduction$', sec_title):
                intro_idx = idx
                break

        if intro_idx > 0:
            # 从 Introduction 往前找，跳过元数据段落，找到第一个真正的正文段
            for idx in range(intro_idx - 1, max(0, intro_idx - 20), -1):
                para = paragraphs[idx]
                text = (para.get('text_content') or para.get('text') or '').strip()
                sec_title = (para.get('section_title') or '').strip()

                # 跳过空段落
                if not text or len(text) < 80:
                    continue
                # 跳过元数据段落
                text_lower = text.lower()
                if any(kw in text_lower for kw in [
                    '@',  # 邮箱
                    'keywords:', 'key words:', 'keyword:',
                    'department', 'university', 'institute', 'laboratory',
                    'school of', 'college of', 'faculty of',
                    '©', 'copyright', 'all rights reserved',
                    'received ', 'accepted ', 'published online',
                    'http://', 'https://', 'doi:',
                    'corresponding author',
                ]):
                    continue
                # 跳过看起来像标题的段落（全大写或标题式大小写，且没有句号结尾）
                if (text.isupper() or (len(text) < 150 and not text.endswith('.') and not text.endswith('。'))) and sec_title:
                    continue
                # 这应该就是摘要
                result['abstract'] = text
                break

    # Truncate overly long fields
    for key in result:
        if len(result[key]) > 5000:
            result[key] = result[key][:5000] + '...'

    return result


# ============================================================
# Main optimizer function
# ============================================================

def optimize_for_journal(parsed_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply journal-aware optimizations to a parsed result.
    Modifies parsed_result in place and returns it.

    Optimizations:
    1. Detect journal family
    2. Re-classify sections using journal-specific headings
    3. Extract volume/issue/pages
    4. Add journal_family to metadata
    """
    metadata = parsed_result.get('metadata', {})
    paragraphs = parsed_result.get('paragraphs', [])

    # Step 1: Detect journal family
    family, detect_method = detect_journal_family(metadata)
    metadata['journal_family'] = family
    metadata['journal_detect_method'] = detect_method

    if family != 'other':
        print(f"   🎯 Journal detected: {family.upper()} (via {detect_method})")

        # Step 2: Re-classify sections using journal-specific headings
        reclassified = 0
        for para in paragraphs:
            old_type = para.get('section_type', 'body')
            section_title = para.get('section_title', '')
            new_type = classify_section_journal_aware(section_title, family)
            if new_type != old_type and new_type != 'body':
                para['section_type'] = new_type
                reclassified += 1

        # Step 2b: Nature-specific — first paragraph is "bold first paragraph"
        # (no heading, ~200 words) and should be classified as abstract.
        # Official: "Articles start with a fully referenced summary paragraph...
        # separate from the main text"
        if family == 'nature' and paragraphs:
            first_para = paragraphs[0]
            if not first_para.get('section_title') and first_para.get('section_type') != 'abstract':
                first_para['section_type'] = 'abstract'
                first_para['section_title'] = '(bold summary paragraph)'
                reclassified += 1
                print(f"   📌 Nature: first paragraph (untitled bold) -> abstract")

        # Step 2c: Record citation style for downstream use
        # Nature: superscript; Science: [1] bracket; Cell: numbered/superscript
        citation_styles = {
            'nature': 'superscript',
            'science': 'bracket',
            'cell': 'numbered',
        }
        metadata['citation_style'] = citation_styles.get(family, 'unknown')

        # Step 2d: Science note — Methods usually in supplementary materials
        if family == 'science':
            metadata['methods_location'] = 'supplementary_materials'
            print(f"   ℹ️  Science: Methods typically in supplementary materials (not main text)")
        elif family == 'nature':
            metadata['methods_location'] = 'after_figure_legends'
        elif family == 'cell':
            metadata['methods_location'] = 'after_figure_legends'

        if reclassified > 0:
            print(f"   📑 Sections re-classified: {reclassified} paragraphs")

        # Step 3: Extract volume/issue/pages
        vol_issue_pages = extract_volume_issue_pages(metadata, family)
        for key, val in vol_issue_pages.items():
            if val and not metadata.get(key):
                metadata[key] = val
        if any(vol_issue_pages.values()):
            print(f"   📚 Volume/Issue/Pages: {vol_issue_pages}")

        # Step 4 (V25.18): Extract abstract, affiliations, funding
        meta_fields = extract_metadata_fields(parsed_result, family)
        for key, val in meta_fields.items():
            if val and not metadata.get(key):
                metadata[key] = val
        extracted_fields = [k for k, v in meta_fields.items() if v]
        if extracted_fields:
            print(f"   📝 Metadata extracted: {', '.join(extracted_fields)}")

    else:
        # Even for "other" journals, try to extract metadata fields
        meta_fields = extract_metadata_fields(parsed_result, family)
        for key, val in meta_fields.items():
            if val and not metadata.get(key):
                metadata[key] = val
        extracted_fields = [k for k, v in meta_fields.items() if v]
        if extracted_fields:
            print(f"   📝 Metadata extracted (generic): {', '.join(extracted_fields)}")
        print(f"   ℹ️  Journal family not specifically detected; using generic optimization")

    parsed_result['metadata'] = metadata
    return parsed_result


# ============================================================
# Standalone test
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Journal Optimizer Test")
    print("=" * 60)

    # Test 1: Nature detection via DOI
    meta1 = {'doi': '10.1038/s41586-020-1234-5', 'journal': 'Nature'}
    family1, method1 = detect_journal_family(meta1)
    print(f"\nTest 1 (Nature DOI): family={family1}, method={method1}")
    assert family1 == 'nature', f"Expected 'nature', got '{family1}'"

    # Test 2: Cell detection via DOI
    meta2 = {'doi': '10.1016/j.cell.2020.01.001', 'journal': 'Cell'}
    family2, method2 = detect_journal_family(meta2)
    print(f"Test 2 (Cell DOI): family={family2}, method={method2}")
    assert family2 == 'cell', f"Expected 'cell', got '{family2}'"

    # Test 3: Science detection via DOI
    meta3 = {'doi': '10.1126/science.abc1234', 'journal': 'Science'}
    family3, method3 = detect_journal_family(meta3)
    print(f"Test 3 (Science DOI): family={family3}, method={method3}")
    assert family3 == 'science', f"Expected 'science', got '{family3}'"

    # Test 4: Cell STAR Methods classification
    sec_type = classify_section_journal_aware('STAR Methods', 'cell')
    print(f"\nTest 4 (Cell STAR Methods): section_type={sec_type}")
    assert sec_type == 'methods', f"Expected 'methods', got '{sec_type}'"

    # Test 4b: Cell STAR Methods sub-headings (official 4 sections)
    for heading in ['Resource Availability', 'Experimental Model and Subject Details',
                    'Method Details', 'Quantification and Statistical Analysis',
                    'Key Resources Table']:
        sec_type = classify_section_journal_aware(heading, 'cell')
        assert sec_type == 'methods', f"Cell '{heading}' -> expected 'methods', got '{sec_type}'"
    print(f"Test 4b (Cell STAR Methods sub-headings): all 5 -> methods ✅")

    # Test 5: Nature online-only Methods classification
    sec_type = classify_section_journal_aware('Online-only Methods', 'nature')
    print(f"Test 5 (Nature Online-only Methods): section_type={sec_type}")
    assert sec_type == 'methods', f"Expected 'methods', got '{sec_type}'"

    # Test 5b: Nature Methods References classification
    sec_type = classify_section_journal_aware('Methods References', 'nature')
    print(f"Test 5b (Nature Methods References): section_type={sec_type}")
    assert sec_type == 'references', f"Expected 'references', got '{sec_type}'"

    # Test 6: Cell Summary classification
    sec_type = classify_section_journal_aware('Summary', 'cell')
    print(f"Test 6 (Cell Summary): section_type={sec_type}")
    assert sec_type == 'abstract', f"Expected 'abstract', got '{sec_type}'"

    # Test 6b: Nature does NOT use "Summary" heading — it should NOT match as abstract
    # (Nature's first para is untitled bold; handled specially in optimize_for_journal)
    sec_type = classify_section_journal_aware('Summary', 'nature')
    print(f"Test 6b (Nature 'Summary' heading): section_type={sec_type} (should be 'body' — Nature uses untitled bold para)")
    # Note: 'summary' is not in NATURE_HEADINGS, so it falls through to 'body'
    # This is correct per official Nature formatting guide

    # Test 7: Nature first paragraph (untitled bold) -> abstract
    nature_result = {
        'metadata': {'doi': '10.1038/s41586-020-1234-5', 'journal': 'Nature', 'title': 'Test'},
        'paragraphs': [
            {'para_id': 'p1', 'para_index': 1, 'section_type': 'body', 'section_title': '',
             'text_content': 'Here we show that... (bold summary paragraph)'},
            {'para_id': 'p2', 'para_index': 2, 'section_type': 'body', 'section_title': 'Results',
             'text_content': '...'},
            {'para_id': 'p3', 'para_index': 3, 'section_type': 'body', 'section_title': 'Methods',
             'text_content': '...'},
        ],
    }
    optimized = optimize_for_journal(nature_result)
    print(f"\nTest 7 (Nature untitled first para -> abstract):")
    print(f"  first para: title='{optimized['paragraphs'][0]['section_title']}' "
          f"type={optimized['paragraphs'][0]['section_type']}")
    assert optimized['paragraphs'][0]['section_type'] == 'abstract', \
        f"Expected first para -> 'abstract', got '{optimized['paragraphs'][0]['section_type']}'"
    assert optimized['metadata']['citation_style'] == 'superscript'
    assert optimized['metadata']['methods_location'] == 'after_figure_legends'

    # Test 8: Science methods in supplementary materials
    science_result = {
        'metadata': {'doi': '10.1126/science.abc1234', 'journal': 'Science', 'title': 'Test'},
        'paragraphs': [
            {'para_id': 'p1', 'section_type': 'body', 'section_title': 'Abstract', 'text_content': '...'},
            {'para_id': 'p2', 'section_type': 'body', 'section_title': 'Results', 'text_content': '...'},
        ],
    }
    optimized = optimize_for_journal(science_result)
    print(f"\nTest 8 (Science methods_location): {optimized['metadata']['methods_location']}")
    assert optimized['metadata']['methods_location'] == 'supplementary_materials'
    assert optimized['metadata']['citation_style'] == 'bracket'

    print("\n✅ All tests passed!")
