"""
Query expansion: multi-query rewriting + optional HyDE.
V22.1 - T2 retrieval enhancement.

Deterministic multi-query (no LLM required):
  Generate 2-4 semantically-equivalent query variants from the user's raw
  question, retrieve each one, and fuse all results with RRF. This boosts
  recall when the user's phrasing differs from how authors write.

Optional HyDE (Hypothetical Document Embeddings):
  If an LLM generation callable is supplied, generate a short hypothetical
  answer paragraph and use its embedding for an additional vector-search
  pass. HyDE queries live in "document space" rather than "question space",
  which often improves vector recall. If no LLM is available, HyDE is
  silently skipped — the rest of the expansion still works.

Usage (standalone test):
  python -m services.search.query_expander
"""
import re
from typing import List, Optional, Callable

# V25.19: 学术缩写扩展
from services.search.abbreviation_expander import AbbreviationExpander

# ---------------------------------------------------------------------------
# Deterministic query rewriting
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
}

# Question-framing prefixes to strip for a "simplified" variant.
QUESTION_PREFIX = re.compile(
    r"^\s*(how\s+(does|do|is|are|can|could|would|will)\s+"
    r"|what\s+(is|are|does|do|causes?|caused?)\s+"
    r"|why\s+(does|do|is|are)\s+"
    r"|explain\s+"
    r"|describe\s+"
    r"|summarize\s+"
    r"|tell\s+me\s+(about|how|what)\s+"
    r"|give\s+me\s+(an?\s+)?(overview|summary|explanation)\s+(of|about)?\s*)",
    re.IGNORECASE,
)

# Entities: capitalized multi-word terms, gene/protein symbols (STAT1, IFN-γ),
# and ALL-CAPS acronyms (JAK, PBMC, MHC-II).
ENTITY_PATTERN = re.compile(
    r"\b("
    r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}"   # Capitalized multi-word
    r"|[A-Z]{2,}(?:[-/][A-Za-z0-9]+)*\d*"          # Acronyms (JAK, MHC-II, STAT1)
    r"|[A-Z][A-Za-z]*\d+(?:[a-z])?"                 # Gene/protein (STAT1, p53, SOCS1)
    r"|IFN[-\s]?[αβγλωκδε]?"                         # Interferon subtypes
    r"|IL-\d+"                                        # Interleukins
    r")\b"
)


def _extract_keywords(query: str) -> List[str]:
    """Meaningful words after removing stop words and punctuation."""
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def _extract_entities(query: str) -> List[str]:
    """Capitalized terms, gene/protein symbols, acronyms."""
    return [m.group(0) for m in ENTITY_PATTERN.finditer(query)]


def _simplify(query: str) -> str:
    """Strip question-framing prefix, keep the core noun phrase."""
    s = QUESTION_PREFIX.sub("", query).strip()
    # Remove trailing question mark
    s = s.rstrip("?").strip()
    return s


class QueryExpander:
    """
    Generate deterministic query variants + optional HyDE.

    Args:
        max_variants: cap on number of deterministic variants (default 4).
        hyde_generate: optional callable(prompt) -> str. If supplied,
            ``hyde()`` will generate a hypothetical answer paragraph.
    """

    def __init__(self, max_variants: int = 4,
                 hyde_generate: Optional[Callable[[str], str]] = None):
        self.max_variants = max_variants
        self.hyde_generate = hyde_generate
        # V25.19: 学术缩写扩展器
        self.abbrev_expander = AbbreviationExpander()

    def expand(self, query: str) -> List[str]:
        """
        Return a deduplicated list of query variants. The original query is
        always first. Variants are ordered from most-to-least faithful to the
        original; RRF fusion does not depend on order, but keeping the
        original first makes debugging easier.
        """
        if not query or not query.strip():
            return [query]

        variants = [query.strip()]

        # 1. Keyword-only variant (excellent for FTS BM25).
        kws = _extract_keywords(query)
        if kws:
            kw_query = " ".join(kws)
            if kw_query.lower() != query.strip().lower():
                variants.append(kw_query)

        # 2. Entity-focused variant (good for vector + FTS on technical terms).
        ents = _extract_entities(query)
        if ents:
            ent_query = " ".join(ents)
            if ent_query.lower() != query.strip().lower():
                variants.append(ent_query)

        # 3. Simplified variant (strip "how does / what is / explain").
        simp = _simplify(query)
        if simp and simp.lower() != query.strip().lower():
            variants.append(simp)

        # 4. V25.19: Abbreviation-expanded variants (KO → knockout, PD-1 → programmed death 1)
        #    提升生物医学缩写查询的召回率
        abbrev_variants = self.abbrev_expander.get_expansion_variants(
            query.strip(), max_variants=2)
        for av in abbrev_variants[1:]:  # 跳过第一个（原始查询）
            if av.lower() != query.strip().lower():
                variants.append(av)

        # Deduplicate (case-insensitive) while preserving order.
        seen = set()
        unique = []
        for v in variants:
            key = re.sub(r"\s+", " ", v.lower().strip())
            if key and key not in seen:
                seen.add(key)
                unique.append(v)
            if len(unique) >= self.max_variants:
                break
        return unique

    def hyde(self, query: str) -> Optional[str]:
        """
        Generate a hypothetical answer paragraph for HyDE vector search.
        Returns None if no LLM generator is configured.
        """
        if self.hyde_generate is None:
            return None
        prompt = (
            f"Write a concise, factual paragraph (3-5 sentences) that "
            f"directly answers the following scientific question. "
            f"Do not include any preamble or meta-commentary.\n\n"
            f"Question: {query}"
        )
        try:
            return self.hyde_generate(prompt)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    expander = QueryExpander()

    test_queries = [
        "How does STAT1 regulate the interferon immune response?",
        "What is the role of JAK-STAT signaling in cancer immunotherapy?",
        "Explain the mechanism of SOCS1 negative feedback regulation",
        "Which papers first reported STAT1 gain-of-function mutations?",
        "TNNT1 expression in liver fibrosis",
        "总结一下这篇论文的方法",
    ]

    print("=" * 64)
    print("🧭 Query Expander Test (deterministic, no LLM)")
    print("=" * 64)
    for q in test_queries:
        variants = expander.expand(q)
        print(f"\nQ: {q}")
        print(f"   → {len(variants)} variants:")
        for i, v in enumerate(variants):
            print(f"     [{i+1}] {v}")

    print("\n" + "=" * 64)
    print("🧪 HyDE test (no LLM configured → should return None)")
    print("=" * 64)
    result = expander.hyde("How does STAT1 work?")
    print(f"   HyDE result: {result} (None = correctly skipped without LLM)")
