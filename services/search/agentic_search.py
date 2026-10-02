"""
Agentic multi-hop search.
V23.2 - T4 Agentic Search

Iterative retrieval with:
  - Hop budget (default 3): stop after N rounds
  - Duplicate detection: don't re-retrieve paragraphs/papers already seen
  - Coverage guard: check if key entities from the query appear in results;
    if coverage is below threshold, generate supplementary sub-queries
  - Sub-query generation: rule-based (no LLM needed), decompose complex
    queries by focusing on uncovered entities

The agentic searcher wraps UnifiedRetriever and adds an iterative loop.
It is deterministic — all decisions are rule-based, no LLM calls.
"""
import re
from collections import OrderedDict
from typing import Dict, List, Optional, Set, Tuple

from services.search.unified_retriever import UnifiedRetriever


# ---------------------------------------------------------------------------
# NER model lazy loading (V27.6: PubMedBERT NER for gene/protein extraction)
# ---------------------------------------------------------------------------

_ner_model = None
_ner_tokenizer = None
_ner_device = None


def _load_ner_model():
    """Lazy load PubMedBERT NER model for gene/protein extraction."""
    global _ner_model, _ner_tokenizer, _ner_device
    if _ner_model is None:
        from transformers import AutoTokenizer, AutoModelForTokenClassification
        import torch

        model_name = 'pruas/BENT-PubMedBERT-NER-Gene'
        print(f"  📥 Loading NER model: {model_name}...")
        _ner_tokenizer = AutoTokenizer.from_pretrained(model_name)
        # V31.12: 改成自动判断，不强制 use_safetensors
        _ner_model = AutoModelForTokenClassification.from_pretrained(
            model_name,
        )

        # Move to GPU if available
        _ner_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        _ner_model = _ner_model.to(_ner_device)
        _ner_model.eval()
        print(f"  ✅ NER model loaded on {_ner_device}")
    return _ner_model, _ner_tokenizer, _ner_device


def _extract_genes_with_ner(text: str) -> List[str]:
    """
    Extract gene/protein entities using PubMedBERT NER model.
    Returns list of gene names found in text.
    """
    try:
        model, tokenizer, device = _load_ner_model()
        import torch

        # Tokenize
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=512
        ).to(device)

        # Predict
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.argmax(outputs.logits, dim=2)

        # Decode predictions
        tokens = inputs.tokens()
        predicted_labels = predictions[0].cpu().numpy()

        # Extract entities (BIO format)
        entities = []
        current_entity = []

        for token, label_id in zip(tokens, predicted_labels):
            label = model.config.id2label[label_id]

            if label.startswith("B-"):
                # Start of new entity
                if current_entity:
                    entities.append("".join(current_entity).replace("##", ""))
                current_entity = [token.replace("##", "")]
            elif label.startswith("I-") and current_entity:
                # Continue current entity
                current_entity.append(token.replace("##", ""))
            else:
                # Outside entity
                if current_entity:
                    entities.append("".join(current_entity).replace("##", ""))
                    current_entity = []

        # Don't forget the last entity
        if current_entity:
            entities.append("".join(current_entity).replace("##", ""))

        return entities

    except Exception as e:
        print(f"  ⚠️ NER extraction failed: {e}, falling back to rule-based")
        return []


# ---------------------------------------------------------------------------
# Entity extraction (rule-based fallback, no NLP library needed)
# ---------------------------------------------------------------------------

# Common English stop words that are never "key entities"
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "and", "but", "or", "nor", "not", "so", "yet", "both",
    "either", "neither", "each", "every", "all", "any", "few", "more",
    "most", "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "if", "when", "where", "how", "what",
    "which", "who", "whom", "this", "that", "these", "those", "it", "its",
    "i", "me", "my", "we", "our", "you", "your", "he", "him", "his",
    "she", "her", "they", "them", "their", "about", "up", "also",
    "how does", "what is", "what are", "explain", "describe", "summarize",
    "review", "discuss", "compare", "contrast", "analyze", "analyse",
    "role", "mechanism", "pathway", "function", "effect", "impact",
    "regulation", "signaling", "signalling", "response", "immune",
    "cell", "cells", "gene", "genes", "protein", "proteins",
    "paper", "papers", "study", "studies", "research", "article",
    "show", "shows", "shown", "found", "find", "finds", "report",
    "reported", "demonstrate", "demonstrated", "suggest", "suggested",
    "indicate", "indicated", "prove", "proved", "shown",
    "type", "types", "kind", "kinds", "way", "ways", "method", "methods",
    "use", "used", "using", "via", "through", "across", "within",
    "between", "among", "against", "around", "along", "behind", "beyond",
    # 普通动词和形容词
    "regulate", "regulates", "regulating", "regulated",
    "promote", "promotes", "promoting", "promoted",
    "inhibit", "inhibits", "inhibiting", "inhibited",
    "induce", "induces", "inducing", "induced",
    "activate", "activates", "activating", "activated",
    "express", "expresses", "expressing", "expressed",
    "bind", "binds", "binding", "bound",
    # 普通器官和疾病名（单独的词太宽泛）
    "breast", "liver", "lung", "colon", "tumor", "tumour",
    "cancer", "carcinoma", "tissue", "patient", "patients",
}

# Gene/protein name pattern: uppercase letters + digits, e.g. STAT1, JAK2,
# TNNT1, IFN-gamma, IL-27, PD-L1
GENE_PROTEIN_RE = re.compile(
    r"\b[A-Z]{2,}[A-Z0-9-]*\b"  # STAT1, JAK2, PD-L1
    r"|\b[A-Z]{2,}-(?:alpha|beta|gamma|lambda|kappa|epsilon)\b"  # IFN-gamma
    r"|\b(?:IL|IFN|TNF|TGF|VEGF|EGF|FGF|HGF|PDGF|IGF|NGF|BDNF|GDNF|"
    r"CNTF|LIF|OSM|CT|CLC|GCSF|GMCSF|MCSF|EPO|TPO|GH|PRL|LEP|ANGPTL|"
    r"SEMA|NETRIN|SLIT|ROBO|DLL|JAG|NOTCH|WNT|FZD|LRP|DKK|SFRP|RSPO|"
    r"BMP|GDF|NODAL|LEFTY|CERBERUS|CHORDIN|NOGGIN|FOLLISTATIN|GREMLIN)\b"
)

# Method/technique keywords
METHOD_KEYWORDS = {
    "single-cell", "single cell", "rna-seq", "rnaseq", "scrna-seq",
    "mass cytometry", "cytof", "flow cytometry", "western blot", "pcr",
    "qpcr", "elisa", "microarray", "crispr", "knockout", "knockdown",
    "immunohistochemistry", "ihc", "immunofluorescence", "if",
    "co-immunoprecipitation", "coip", "chip-seq", "atac-seq", "hic",
    "proteomics", "genomics", "transcriptomics", "metabolomics",
    "machine learning", "deep learning", "neural network", "random forest",
    "support vector machine", "svm", "clustering", "pca", "umap", "tsne",
    "differential expression", "gene set enrichment", "gsea", "pathway analysis",
}


def extract_key_entities(query: str) -> List[str]:
    """
    Extract key entities from a query (gene/protein names + method keywords
    + significant non-stop-word terms).

    V27.6:优先用 NER 模型提取基因实体，失败了再用基于规则的方法兜底。

    Returns a deduplicated list of entity strings, most specific first.
    """
    q = query.strip()
    entities: List[str] = []
    seen: Set[str] = set()

    def add(e: str):
        e = e.strip().rstrip(".,;:!?")
        if e and e.lower() not in STOP_WORDS and len(e) > 1 and e.lower() not in seen:
            seen.add(e.lower())
            entities.append(e)

    # 1. Gene/protein names (highest priority) — V27.6: 先用 NER 模型
    ner_genes = _extract_genes_with_ner(q)
    for gene in ner_genes:
        add(gene)

    # 2. 基于规则的基因名提取（兜底）
    for m in GENE_PROTEIN_RE.finditer(q):
        add(m.group(0))

    # 3. Method keywords
    q_lower = q.lower()
    for kw in METHOD_KEYWORDS:
        if kw in q_lower:
            add(kw)

    # 4. Capitalized multi-word terms (e.g. "JAK-STAT pathway", "interferon
    #    gamma", "type I interferon") — capture consecutive capitalized words
    cap_phrases = re.findall(
        r"\b(?:[A-Z][a-z]+(?:-[A-Z]?[a-z]+)?\s+){1,3}[A-Z][a-z]+\b", q)
    for phrase in cap_phrases:
        # Filter out phrases that are mostly stop words
        words = phrase.lower().split()
        content_words = [w for w in words if w not in STOP_WORDS]
        if len(content_words) >= 1:
            add(phrase)

    # 5. Remaining significant single words (nouns-ish: length > 3, not stop)
    for word in re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", q):
        w_lower = word.lower()
        if w_lower not in STOP_WORDS and w_lower not in seen:
            # Only add if it looks like a content word (not a common verb/adj)
            if not w_lower.endswith(("ing", "ed")) or w_lower in METHOD_KEYWORDS:
                add(word)

    return entities


# ---------------------------------------------------------------------------
# Agentic Searcher
# ---------------------------------------------------------------------------

class AgenticSearcher:
    """
    Multi-hop agentic search wrapper around UnifiedRetriever.

    Workflow per query:
      1. Initial retrieval (hop 0)
      2. Extract key entities from query
      3. Check coverage: what fraction of entities appear in retrieved text?
      4. If coverage < threshold and hops remain:
         a. Identify uncovered entities
         b. Generate sub-queries (original query + focused entity)
         c. Retrieve again, tracking seen para_ids/paper_ids
         d. Merge new results (deduplicate)
      5. Return merged envelope with hop metadata
    """

    def __init__(self, retriever: Optional[UnifiedRetriever] = None,
                 max_hops: int = 3,
                 min_coverage: float = 0.6,
                 max_subqueries_per_hop: int = 2):
        self.retriever = retriever or UnifiedRetriever(
            rerank=True, routing=True, expand=True, graph_expand=True)
        self.max_hops = max_hops
        self.min_coverage = min_coverage
        self.max_subqueries = max_subqueries_per_hop

    # ------------------------------------------------------------------
    # Coverage check
    # ------------------------------------------------------------------
    def _check_coverage(self, entities: List[str],
                         all_text: str) -> Tuple[float, List[str], List[str]]:
        """
        Check what fraction of entities appear in the retrieved text.

        Returns: (coverage_ratio, covered_entities, uncovered_entities)
        """
        if not entities:
            return 1.0, [], []

        text_lower = all_text.lower()
        covered = []
        uncovered = []
        for e in entities:
            if e.lower() in text_lower:
                covered.append(e)
            else:
                uncovered.append(e)

        ratio = len(covered) / len(entities)
        return ratio, covered, uncovered

    # ------------------------------------------------------------------
    # Sub-query generation
    # ------------------------------------------------------------------
    def _generate_subqueries(self, original_query: str,
                              uncovered_entities: List[str]) -> List[str]:
        """
        Generate focused sub-queries for uncovered entities.

        Strategy: combine original query keywords with the uncovered entity.
        Deterministic, no LLM.
        """
        subqueries = []
        # Extract core noun phrase from original query (strip question words)
        core = re.sub(
            r"^(?:how does|what is|what are|explain|describe|summarize|"
            r"review|discuss|compare|analyze|analyse|tell me about)\s+",
            "", original_query, flags=re.IGNORECASE).strip()

        for entity in uncovered_entities[:self.max_subqueries]:
            # Sub-query: entity + core context
            sq = f"{entity} {core}" if core else entity
            subqueries.append(sq.strip())

        return subqueries

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    @staticmethod
    def _dedup_paragraphs(paragraphs: List[Dict]) -> List[Dict]:
        """Remove duplicate paragraphs by para_id, keep first (highest score)."""
        seen = set()
        result = []
        for p in paragraphs:
            pid = p.get("para_id") or p.get("id") or id(p)
            if pid not in seen:
                seen.add(pid)
                result.append(p)
        return result

    @staticmethod
    def _dedup_papers(papers: List[Dict], id_key: str = "paper_id") -> List[Dict]:
        """Remove duplicate papers by paper_id."""
        seen = set()
        result = []
        for p in papers:
            pid = p.get(id_key)
            if pid and pid not in seen:
                seen.add(pid)
                result.append(p)
        return result

    # ------------------------------------------------------------------
    # Main search
    # ------------------------------------------------------------------
    def search(self, query: str, **kwargs) -> Dict:
        """
        Run multi-hop agentic search.

        Returns a merged envelope with additional fields:
          - hops: list of {hop, query, coverage, new_paragraphs, new_papers}
          - final_coverage: float
          - total_hops: int
          - all other fields from UnifiedRetriever.retrieve()
        """
        top_paragraphs = kwargs.get("top_paragraphs", 6)
        top_figures = kwargs.get("top_figures", 3)
        paper_id = kwargs.get("paper_id")

        # Extract key entities upfront
        entities = extract_key_entities(query)

        # Hop 0: initial retrieval
        result = self.retriever.retrieve(
            query, paper_id=paper_id,
            top_paragraphs=top_paragraphs, top_figures=top_figures)

        # Collect all retrieved text for coverage check
        all_text = self._collect_text(result)
        coverage, covered, uncovered = self._check_coverage(entities, all_text)

        hops = [{
            "hop": 0,
            "query": query,
            "coverage": round(coverage, 3),
            "covered_entities": covered,
            "uncovered_entities": uncovered,
            "new_paragraphs": len(result.get("paragraphs", [])),
            "new_papers": len(result.get("papers", [])),
        }]

        # Track seen IDs for deduplication
        seen_para_ids: Set[str] = set(
            p.get("para_id") for p in result.get("paragraphs", []) if p.get("para_id"))
        seen_paper_ids: Set[str] = set(
            p.get("paper_id") for p in result.get("papers", []) if p.get("paper_id"))

        # Iterative hops
        current_hop = 0
        while (coverage < self.min_coverage
               and current_hop < self.max_hops
               and uncovered):
            current_hop += 1

            # Generate sub-queries for uncovered entities
            subqueries = self._generate_subqueries(query, uncovered)
            if not subqueries:
                break

            hop_new_paras = 0
            hop_new_papers = 0

            for sq in subqueries:
                try:
                    sub_result = self.retriever.retrieve(
                        sq, paper_id=paper_id,
                        top_paragraphs=top_paragraphs,
                        top_figures=top_figures)
                except Exception:
                    continue

                # Merge paragraphs (deduplicate)
                new_paras = [
                    p for p in sub_result.get("paragraphs", [])
                    if p.get("para_id") and p["para_id"] not in seen_para_ids
                ]
                for p in new_paras:
                    seen_para_ids.add(p["para_id"])
                result["paragraphs"].extend(new_paras)
                hop_new_paras += len(new_paras)

                # Merge parent contexts
                if sub_result.get("parent_contexts"):
                    existing_ctx_ids = set(
                        c.get("paper_id", "") + str(c.get("section", ""))
                        for c in result.get("parent_contexts", []))
                    for ctx in sub_result["parent_contexts"]:
                        ctx_key = ctx.get("paper_id", "") + str(ctx.get("section", ""))
                        if ctx_key not in existing_ctx_ids:
                            existing_ctx_ids.add(ctx_key)
                            result.setdefault("parent_contexts", []).append(ctx)

                # Merge figures/tables (deduplicate by id)
                for field in ("figures", "tables"):
                    existing_ids = set(
                        f.get(f"{field[:-1]}_id") for f in result.get(field, []))
                    for item in sub_result.get(field, []):
                        iid = item.get(f"{field[:-1]}_id")
                        if iid and iid not in existing_ids:
                            existing_ids.add(iid)
                            result.setdefault(field, []).append(item)

                # Merge papers (deduplicate)
                new_papers = [
                    p for p in sub_result.get("papers", [])
                    if p.get("paper_id") and p["paper_id"] not in seen_paper_ids
                ]
                for p in new_papers:
                    seen_paper_ids.add(p["paper_id"])
                result.setdefault("papers", []).extend(new_papers)
                hop_new_papers += len(new_papers)

                # Merge graph neighbors
                if sub_result.get("graph_neighbors"):
                    existing_g_ids = set(
                        g.get("paper_id") for g in result.get("graph_neighbors", []))
                    for g in sub_result["graph_neighbors"]:
                        if g.get("paper_id") and g["paper_id"] not in existing_g_ids:
                            existing_g_ids.add(g["paper_id"])
                            result.setdefault("graph_neighbors", []).append(g)

            # Re-check coverage after this hop
            all_text = self._collect_text(result)
            coverage, covered, uncovered = self._check_coverage(entities, all_text)

            hops.append({
                "hop": current_hop,
                "queries": subqueries,
                "coverage": round(coverage, 3),
                "covered_entities": covered,
                "uncovered_entities": uncovered,
                "new_paragraphs": hop_new_paras,
                "new_papers": hop_new_papers,
            })

            # If no new content was added, stop to avoid infinite loop
            if hop_new_paras == 0 and hop_new_papers == 0:
                break

        # Final: cap results to requested top_k
        if len(result.get("paragraphs", [])) > top_paragraphs * 2:
            result["paragraphs"] = result["paragraphs"][:top_paragraphs * 2]

        result["hops"] = hops
        result["final_coverage"] = round(coverage, 3)
        result["total_hops"] = current_hop
        result["key_entities"] = entities
        result["covered_entities"] = covered
        result["uncovered_entities"] = uncovered

        return result

    # ------------------------------------------------------------------
    # Helper: collect all text from a result dict for coverage checking
    # ------------------------------------------------------------------
    @staticmethod
    def _collect_text(result: Dict) -> str:
        parts = []
        for p in result.get("paragraphs", []):
            parts.append(p.get("text", ""))
        for ctx in result.get("parent_contexts", []):
            parts.append(ctx.get("text", ""))
        for f in result.get("figures", []):
            parts.append(f.get("caption", ""))
        for t in result.get("tables", []):
            parts.append(t.get("caption", ""))
            parts.append(t.get("markdown", ""))
        for p in result.get("papers", []):
            parts.append(p.get("title", ""))
        return " ".join(parts)


# ======================================================================
# Self-test
# ======================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 Agentic Multi-Hop Search Test (V23.2)")
    print("=" * 60)

    # Test entity extraction
    print("\n── Entity extraction tests ──")
    test_queries = [
        "How does STAT1 regulate the interferon immune response?",
        "What is the role of JAK-STAT signaling in cancer immunotherapy?",
        "Explain the mechanism of SOCS1 negative feedback regulation",
        "TNNT1 expression in liver fibrosis",
        "Compare single-cell RNA-seq and mass cytometry for immune profiling",
    ]
    for q in test_queries:
        entities = extract_key_entities(q)
        print(f"  Q: {q}")
        print(f"     → entities: {entities}")

    # Test agentic search
    print("\n── Agentic search (may take a while — loads models) ──")
    agentic = AgenticSearcher(max_hops=2, min_coverage=0.5)
    query = "How does STAT1 regulate the interferon immune response?"
    print(f"  Query: {query}")
    result = agentic.search(query, top_paragraphs=4)

    print(f"\n  Key entities: {result['key_entities']}")
    print(f"  Covered: {result['covered_entities']}")
    print(f"  Uncovered: {result['uncovered_entities']}")
    print(f"  Final coverage: {result['final_coverage']}")
    print(f"  Total hops: {result['total_hops']}")
    print(f"  Total paragraphs: {len(result.get('paragraphs', []))}")
    print(f"  Total papers: {len(result.get('papers', []))}")

    print("\n  Hop details:")
    for hop in result["hops"]:
        print(f"    Hop {hop['hop']}: coverage={hop['coverage']}, "
              f"new_paras={hop['new_paragraphs']}, "
              f"new_papers={hop['new_papers']}")

    print("\n✅ Agentic search test complete.")
