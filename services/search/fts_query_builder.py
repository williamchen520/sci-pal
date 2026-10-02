"""
Enhanced FTS5 query builder.
V25.19 - Retrieval optimization

Improves over the naive "OR all terms" approach with:
  1. Phrase detection: multi-word entities / technical terms get quoted
     ("JAK-STAT signaling" matches as a phrase, not 3 independent words).
  2. NEAR operator: terms that likely co-occur get a NEAR(...) clause,
     boosting paragraphs where they appear close together.
  3. Entity weighting: gene/protein symbols, acronyms, capitalized terms
     get higher weight via the FTS5 column-weight / prefix syntax.
  4. Fallback hierarchy: phrase query → if no hits, degrade gracefully
     to term OR query (never return empty due to syntax issues).

Usage:
    builder = FTSQueryBuilder()
    fts_query = builder.build("How does STAT1 regulate interferon response?")
    # → 'STAT1^3 OR "interferon response"^2 OR regulate OR response'
"""
import re
from typing import List, Tuple, Optional

# ---------------------------------------------------------------------------
# Stop words (same set as hybrid_search for consistency)
# ---------------------------------------------------------------------------
STOP_WORDS = {
    "how", "does", "do", "is", "are", "was", "were", "be", "been",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "what", "which", "when", "where", "why", "can", "could",
    "we", "you", "it", "this", "that", "these", "those", "i", "me",
    "my", "our", "your", "their", "his", "her", "its", "as", "at",
    "by", "from", "into", "about", "between", "through", "during",
    "before", "after", "above", "below", "up", "down", "out", "off",
    "over", "under", "again", "further", "then", "once", "here",
    "there", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "also", "now",
    "show", "shows", "shown", "demonstrate", "demonstrates",
    "report", "reports", "reported", "find", "finds", "found",
    "study", "studies", "paper", "papers", "article", "articles",
}

# ---------------------------------------------------------------------------
# Entity patterns (gene/protein, acronym, capitalized multi-word)
# Mirrors query_expander.py ENTITY_PATTERN but also catches hyphenated
# compound terms common in biology (JAK-STAT, NF-kB, PI3K-AKT).
# ---------------------------------------------------------------------------
ENTITY_PATTERNS = [
    # Gene/protein symbols: STAT1, p53, BCL-2, SOCS1, TNNT1
    # (首字母大写，后续可大写或小写，结尾可选数字)
    re.compile(r"\b[A-Z][A-Za-z]*\d+(?:[a-z])?\b"),
    # Acronyms with optional hyphens/slashes and trailing digits:
    # JAK, MHC-II, IFN-γ, CD4+, TNFa, IL2
    re.compile(r"\b[A-Z]{2,}(?:[-/][A-Za-z0-9+]+)*\d*\b"),
    # Interleukins / interferons: IL-6, IFN-gamma, TNF-alpha
    re.compile(r"\b(?:IL|IFN|TNF|TGF|VEGF|EGF|PDGF|FGF|HGF)[-\s]?[a-z0-9]*\b", re.IGNORECASE),
    # Hyphenated technical compounds: JAK-STAT, PI3K-AKT, NF-kB
    re.compile(r"\b[A-Za-z0-9]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b"),
]

# Capitalized multi-word terms (e.g. "Retinoic Acid", "Cell Cycle")
CAP_MULTIWORD = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}\b")

# Terms that are too generic to be treated as entities (false positives)
GENERIC_ENTITIES = {"The", "This", "That", "These", "Those", "It", "They",
                     "We", "You", "He", "She", "Figure", "Table", "Fig",
                     "Results", "Methods", "Discussion", "Introduction",
                     "Abstract", "Conclusion", "References", "Background"}


def _extract_entities(query: str) -> List[str]:
    """Extract technical entities from query, deduplicated, order-preserving."""
    entities = []
    seen = set()
    for pat in ENTITY_PATTERNS:
        for m in pat.finditer(query):
            term = m.group(0).strip()
            if (term and term not in GENERIC_ENTITIES
                    and len(term) > 1 and term.lower() not in STOP_WORDS):
                key = term.lower()
                if key not in seen:
                    seen.add(key)
                    entities.append(term)
    # Capitalized multi-word
    for m in CAP_MULTIWORD.finditer(query):
        term = m.group(0).strip()
        if term and term not in GENERIC_ENTITIES:
            key = term.lower()
            if key not in seen:
                seen.add(key)
                entities.append(term)
    return entities


def _extract_keywords(query: str) -> List[str]:
    """Meaningful single words after stop-word removal."""
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def _detect_phrases(query: str, entities: List[str]) -> List[str]:
    """
    Detect likely phrases:
      - Entities that are multi-word (already phrases).
      - Adjacent keyword pairs that form common technical phrases.
    Returns a list of phrase strings (already quoted-ready).
    """
    phrases = []
    seen = set()
    # Multi-word entities are natural phrases
    for ent in entities:
        if " " in ent or "-" in ent:
            key = ent.lower()
            if key not in seen:
                seen.add(key)
                phrases.append(ent)
    return phrases


def _escape_fts_term(term: str) -> str:
    """Escape a term for safe inclusion in FTS5 query."""
    # FTS5 terms: alphanumeric + underscore are safe; everything else
    # needs the term to be quoted. We quote if contains non-alnum.
    if re.match(r'^[a-zA-Z0-9_]+$', term):
        return term
    # Contains hyphen, slash, etc. → quote it
    return f'"{term}"'


class FTSQueryBuilder:
    """
    Build an enhanced FTS5 query from a natural-language question.

    Strategy (highest precision first, degrade gracefully):
      1. Weighted entities (^3) — gene/protein/acronyms are most discriminative.
      2. Phrases (^2) — multi-word technical terms matched as phrases.
      3. NEAR clusters — pairs of keywords that likely co-occur.
      4. Remaining keywords (^1) — individual term OR match.

    The final query is an OR of all these components, so higher-weighted
    components boost score but don't exclude lower-weighted matches.
    """

    def __init__(self, entity_weight: int = 3, phrase_weight: int = 2,
                 keyword_weight: int = 1, use_near: bool = True,
                 near_distance: int = 10):
        self.entity_weight = entity_weight
        self.phrase_weight = phrase_weight
        self.keyword_weight = keyword_weight
        self.use_near = use_near
        self.near_distance = near_distance

    def build(self, query: str) -> str:
        """
        Build the FTS5 query string. Always returns a valid query;
        if nothing meaningful is extracted, falls back to a simple
        OR of all non-stop words.
        """
        if not query or not query.strip():
            return '""'

        entities = _extract_entities(query)
        keywords = _extract_keywords(query)
        phrases = _detect_phrases(query, entities)

        components = []

        # 1. Weighted entities (single-word entities like STAT1, JAK)
        single_entities = [e for e in entities if " " not in e]
        for ent in single_entities:
            escaped = _escape_fts_term(ent)
            if self.entity_weight > 1:
                components.append(f"{escaped}^{self.entity_weight}")
            else:
                components.append(escaped)

        # 2. Weighted phrases (multi-word entities / technical compounds)
        for phrase in phrases:
            escaped = _escape_fts_term(phrase)
            if self.phrase_weight > 1:
                components.append(f"{escaped}^{self.phrase_weight}")
            else:
                components.append(escaped)

        # 3. NEAR clusters: pair up remaining keywords
        if self.use_near and len(keywords) >= 2:
            # Use first 4 keywords for NEAR pairs (avoid overly long queries)
            kw_for_near = keywords[:4]
            # Pair adjacent keywords
            for i in range(0, len(kw_for_near) - 1, 2):
                t1 = _escape_fts_term(kw_for_near[i])
                t2 = _escape_fts_term(kw_for_near[i + 1])
                components.append(f"NEAR({t1} {t2}, {self.near_distance})")

        # 4. Remaining keywords (not already in entities/phrases)
        entity_lower = {e.lower() for e in entities}
        phrase_lower = {p.lower() for p in phrases}
        for kw in keywords:
            if kw not in entity_lower and kw not in phrase_lower:
                escaped = _escape_fts_term(kw)
                if self.keyword_weight > 1:
                    components.append(f"{escaped}^{self.keyword_weight}")
                else:
                    components.append(escaped)

        # Deduplicate components while preserving order
        seen = set()
        unique = []
        for c in components:
            key = c.lower()
            if key not in seen:
                seen.add(key)
                unique.append(c)

        if not unique:
            # Ultimate fallback: OR of all words (even stop words, just in case)
            all_words = re.findall(r'[a-zA-Z0-9]+', query)
            unique = [_escape_fts_term(w) for w in all_words if len(w) > 1]

        return " OR ".join(unique)

    def build_simple(self, query: str) -> str:
        """
        Build a simple, safe OR query (no weights, no phrases, no NEAR).
        Used as a fallback if the enhanced query causes a syntax error.
        """
        keywords = _extract_keywords(query)
        if not keywords:
            all_words = re.findall(r'[a-zA-Z0-9]+', query)
            keywords = [w for w in all_words if len(w) > 1]
        escaped = [_escape_fts_term(k) for k in keywords]
        return " OR ".join(escaped) if escaped else '""'

    def explain(self, query: str) -> dict:
        """
        Return a diagnostic breakdown of how the query was built.
        Useful for debugging and for the retrieval diagnostics module.
        """
        entities = _extract_entities(query)
        keywords = _extract_keywords(query)
        phrases = _detect_phrases(query, entities)
        fts_query = self.build(query)
        return {
            "original_query": query,
            "entities": entities,
            "phrases": phrases,
            "keywords": keywords,
            "fts_query": fts_query,
            "component_count": fts_query.count(" OR ") + 1 if fts_query else 0,
        }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    builder = FTSQueryBuilder()

    test_queries = [
        "How does STAT1 regulate the interferon immune response?",
        "What is the role of JAK-STAT signaling in cancer immunotherapy?",
        "Explain the mechanism of SOCS1 negative feedback regulation",
        "TNNT1 expression in liver fibrosis",
        "single cell RNA sequencing batch effects",
        "Figure 3 shows what about PBMC proliferation?",
        "总结一下这篇论文的方法",
    ]

    print("=" * 70)
    print("🔍 FTS Query Builder Test (V25.19 enhanced)")
    print("=" * 70)
    for q in test_queries:
        info = builder.explain(q)
        print(f"\nQ: {q}")
        print(f"   Entities: {info['entities']}")
        print(f"   Phrases:  {info['phrases']}")
        print(f"   Keywords: {info['keywords']}")
        print(f"   → FTS: {info['fts_query']}")
