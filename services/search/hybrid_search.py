"""
Hybrid search: vector + full-text with RRF fusion.
V21.0 - Retrieval layer
V22.1 - Multi-query expansion + optional HyDE
V25.19 - Enhanced FTS query + dynamic RRF weights + MMR diversification + diagnostics
"""
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable
import chromadb

from services.search.reference_filter import is_reference_entry
from services.search.boilerplate_filter import clean_boilerplate
from services.search.query_expander import QueryExpander
from services.search.fts_query_builder import FTSQueryBuilder
from services.search.mmr_diversifier import MMRDiversifier
from services.search.retrieval_diagnostics import RetrievalDiagnostics
from services.search.dedup import suppress_near_duplicates, threshold_from_env

from config.paths import CHROMA_PATH, DB_PATH, EMBEDDING_MODEL
RRF_K = 60  # RRF constant
VECTOR_TOP_K = 20
FTS_TOP_K = 20
FINAL_TOP_K = 10

# Drop bibliography entries from QA paragraph retrieval (they live in the
# citations table). Set False to restore raw recall when auditing.
EXCLUDE_REFERENCE_ENTRIES = True

# Strip front-matter boilerplate lines (editor info, affiliations, copyright,
# DOI links) from returned paragraph text. Works line-by-line so real body
# text mixed into the same paragraph is preserved.
CLEAN_BOILERPLATE = True

# Multi-query expansion (V22.1): generate 2-4 query variants and fuse all
# results with RRF. Set False to use only the original query.
MULTI_QUERY = True
MAX_QUERY_VARIANTS = 4

# V25.19: Enhanced FTS query (phrase matching + NEAR + entity weighting)
ENHANCED_FTS = True

# V25.19: Dynamic RRF weights — adjust vector/FTS balance based on query type.
# Entity-heavy queries (lots of gene/protein symbols) get higher FTS weight.
# Natural-language queries get higher vector weight.
DYNAMIC_RRF_WEIGHTS = True
DEFAULT_VECTOR_WEIGHT = 1.0
DEFAULT_FTS_WEIGHT = 1.0
ENTITY_FTS_WEIGHT_BOOST = 0.5  # extra FTS weight per entity (capped at +1.0)

# V25.19: MMR diversification — reduce redundant paragraphs from same paper/section.
MMR_DIVERSIFY = True
MMR_LAMBDA = 0.6  # 1.0 = pure relevance, 0.5 = balanced diversity
# V25.23: 根据调优脚本结果，默认值从 0.7 改为 0.6
# （λ=0.6 在真实数据库上多样性和 λ=0.5 相同，但相关性更高）


def chroma_paper_filter(paper_ids) -> Dict[str, List[str]]:
    """Chroma expects a list for $in; callers often pass a set."""
    return {"$in": list(paper_ids)}


class HybridSearch:
    def __init__(self, hyde_generate: Optional[Callable[[str], str]] = None,
                 diagnostics: bool = False):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        collection_name = os.environ.get("SCIPAL_PARAGRAPH_COLLECTION", "paragraphs")
        self.para_collection = self.client.get_collection(collection_name)
        self.contextual_collection = self._get_collection("paragraphs_contextual")
        self.paper_collection = self._get_collection("papers")
        self.fig_collection = self._get_collection("figures")
        self.table_collection = self._get_collection("tables")
        self.chunk_collection = self._get_collection("chunks")  # V24.1

        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(EMBEDDING_MODEL)

        # V22.1: query expander (deterministic multi-query + optional HyDE).
        self.query_expander = QueryExpander(
            max_variants=MAX_QUERY_VARIANTS,
            hyde_generate=hyde_generate,
        )

        # V25.19: enhanced FTS query builder
        if ENHANCED_FTS:
            self.fts_builder = FTSQueryBuilder()

        # V25.19: MMR diversifier
        if MMR_DIVERSIFY:
            self.mmr = MMRDiversifier(lambda_param=MMR_LAMBDA)

        # V25.19: retrieval diagnostics
        self.diagnostics = RetrievalDiagnostics(enabled=diagnostics)

    def _get_collection(self, name):
        """Get a collection if it exists, else None."""
        try:
            return self.client.get_collection(name)
        except Exception:
            return None

    def _get_filtered_paper_ids(self, filters: Optional[Dict]) -> Optional[List[str]]:
        """
        Resolve year/journal filters to a list of paper_ids.
        Returns None if no paper-level filters are active (meaning "all papers").
        """
        if not filters:
            return None
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        journal = filters.get("journal")
        paper_ids = filters.get("paper_ids")
        if not any([year_min, year_max, journal]) and paper_ids is None:
            return None
        if paper_ids is not None and not any([year_min, year_max, journal]):
            return set(paper_ids)
        if paper_ids is not None and not paper_ids:
            return set()

        clauses = []
        params = []
        if year_min is not None:
            clauses.append("year >= ?")
            params.append(year_min)
        if year_max is not None:
            clauses.append("year <= ?")
            params.append(year_max)
        if journal:
            clauses.append("journal LIKE ?")
            params.append(f"%{journal}%")

        where = " AND ".join(clauses)
        rows = self.conn.execute(
            f"SELECT paper_id FROM papers WHERE {where}", params
        ).fetchall()
        result = [r["paper_id"] for r in rows]
        if paper_ids is not None:
            result = [pid for pid in result if pid in set(paper_ids)]
        return result

    def vector_search(self, query: str, top_k: int = VECTOR_TOP_K,
                      paper_id: str = None,
                      filters: Optional[Dict] = None,
                      collection=None) -> List[Dict]:
        """Semantic search via vector embeddings.

        V24.2: filters dict supports section_l1, year_min, year_max, journal.
        """
        query_emb = self.model.encode([query]).tolist()

        # Build Chroma where clause
        where = {}
        if paper_id:
            where["paper_id"] = paper_id
        # Paper-level filters (year/journal) → resolve to paper_ids
        filtered_pids = self._get_filtered_paper_ids(filters)
        if filtered_pids is not None:
            if not filtered_pids:
                return []  # no papers match the filter
            if "paper_id" in where:
                # Intersect: keep only paper_id if it's in the filtered set
                if where["paper_id"] not in filtered_pids:
                    return []
            else:
                where["paper_id"] = chroma_paper_filter(filtered_pids)
        where = where if where else None

        # Over-fetch so filtering bibliography + section doesn't shrink recall.
        section_filter = (filters or {}).get("section_l1")
        fetch_k = min(top_k * 4, 200) if (EXCLUDE_REFERENCE_ENTRIES or section_filter) else top_k
        target_collection = collection or self.para_collection
        results = target_collection.query(
            query_embeddings=query_emb,
            n_results=fetch_k,
            where=where
        )

        hits = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            text = results["documents"][0][i]
            # V24.2: section filter (post-filter since metadata may vary)
            if section_filter and meta.get("section_l1") != section_filter:
                continue
            if EXCLUDE_REFERENCE_ENTRIES and is_reference_entry(
                text, meta.get("section_l1"), meta.get("section_l2")
            ):
                continue
            if CLEAN_BOILERPLATE:
                text = clean_boilerplate(text)
                if not text:
                    continue
            hits.append({
                "para_id": results["ids"][0][i],
                "paper_id": meta.get("paper_id"),
                "section_l1": meta.get("section_l1"),
                "section_l2": meta.get("section_l2"),
                "text": text,
                "metadata": meta,
                "score": 1.0 - results["distances"][0][i],
            })
            if len(hits) >= top_k:
                break
        return hits

    def fts_search(self, query: str, top_k: int = FTS_TOP_K,
                   paper_id: str = None,
                   filters: Optional[Dict] = None) -> List[Dict]:
        """Full-text search via SQLite FTS5.

        V24.2: filters dict supports section_l1, year_min, year_max, journal.
        Year/journal filters require a JOIN with the papers table.
        V25.19: enhanced FTS query with phrase matching, NEAR, entity weighting.
        """
        # V25.19: use enhanced FTS query builder or fall back to simple
        if ENHANCED_FTS and hasattr(self, "fts_builder"):
            fts_query = self.fts_builder.build(query)
            # Log diagnostics
            if self.diagnostics.enabled:
                info = self.fts_builder.explain(query)
                self.diagnostics.log("fts_query", "fts_query", info["fts_query"])
                self.diagnostics.log("fts_query", "entities", info["entities"])
                self.diagnostics.log("fts_query", "phrases", info["phrases"])
        else:
            import re
            stop_words = {"how", "does", "do", "is", "are", "the", "a", "an",
                          "and", "or", "of", "to", "in", "on", "for", "with",
                          "what", "which", "when", "where", "why", "can", "could",
                          "we", "you", "it", "this", "that", "these", "those"}
            raw_terms = re.findall(r'[a-zA-Z0-9]+', query.lower())
            terms = [t for t in raw_terms if t not in stop_words and len(t) > 1]
            if not terms:
                return []
            fts_query = " OR ".join(terms)

        # V24.2: determine if we need a JOIN with papers for year/journal
        need_paper_join = bool(filters and (
            filters.get("year_min") or filters.get("year_max") or
            filters.get("journal")
        ))
        section_filter = (filters or {}).get("section_l1")

        if need_paper_join:
            sql = """
                SELECT f.para_id, f.paper_id, f.section_l1, f.section_l2,
                       f.text, bm25(paragraphs_fts) as score
                FROM paragraphs_fts f
                JOIN papers p ON f.paper_id = p.paper_id
                WHERE paragraphs_fts MATCH ?
            """
        else:
            sql = """
                SELECT para_id, paper_id, section_l1, section_l2, text,
                       bm25(paragraphs_fts) as score
                FROM paragraphs_fts
                WHERE paragraphs_fts MATCH ?
            """
        params = [fts_query]

        if paper_id:
            sql += " AND paper_id = ?"
            params.append(paper_id)

        paper_ids = (filters or {}).get("paper_ids")
        if paper_ids is not None:
            paper_ids = list(paper_ids)
            if not paper_ids:
                return []
            column = "f.paper_id" if need_paper_join else "paper_id"
            marks = ",".join("?" * len(paper_ids))
            sql += f" AND {column} IN ({marks})"
            params.extend(paper_ids)

        # V24.2: section filter
        if section_filter:
            sql += " AND section_l1 = ?"
            params.append(section_filter)

        # V24.2: year/journal filters (only when JOIN is active)
        if need_paper_join:
            if filters.get("year_min") is not None:
                sql += " AND p.year >= ?"
                params.append(filters["year_min"])
            if filters.get("year_max") is not None:
                sql += " AND p.year <= ?"
                params.append(filters["year_max"])
            if filters.get("journal"):
                sql += " AND p.journal LIKE ?"
                params.append(f"%{filters['journal']}%")

        sql += " ORDER BY score LIMIT ?"
        fetch_k = min(top_k * 3, 200) if EXCLUDE_REFERENCE_ENTRIES else top_k
        params.append(fetch_k)

        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # V25.19: enhanced query may have syntax issues; fall back to simple
            if ENHANCED_FTS and hasattr(self, "fts_builder"):
                fts_query = self.fts_builder.build_simple(query)
                params[0] = fts_query
                try:
                    rows = self.conn.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    return []
            else:
                try:
                    params2 = [terms[0]]
                    if paper_id:
                        params2.append(paper_id)
                    if section_filter:
                        params2.append(section_filter)
                    params2.append(fetch_k)
                    rows = self.conn.execute(sql, params2).fetchall()
                except sqlite3.OperationalError:
                    return []

        hits = []
        for r in rows:
            if EXCLUDE_REFERENCE_ENTRIES and is_reference_entry(
                r["text"], r["section_l1"], r["section_l2"]
            ):
                continue
            hit_text = clean_boilerplate(r["text"]) if CLEAN_BOILERPLATE else r["text"]
            if not hit_text:
                continue
            hits.append({
                "para_id": r["para_id"],
                "paper_id": r["paper_id"],
                "section_l1": r["section_l1"],
                "section_l2": r["section_l2"],
                "text": hit_text,
                "score": -r["score"],  # FTS bm25 is negative, negate
            })
            if len(hits) >= top_k:
                break
        return hits

    def _compute_dynamic_weights(self, query: str) -> Tuple[float, float]:
        """
        V25.19: Compute vector/FTS RRF weights based on query characteristics.

        - Entity-heavy queries (gene/protein/acronyms) → boost FTS (exact match)
        - Natural-language queries (long, few entities) → boost vector (semantics)

        Returns: (vector_weight, fts_weight)
        """
        if not DYNAMIC_RRF_WEIGHTS:
            return DEFAULT_VECTOR_WEIGHT, DEFAULT_FTS_WEIGHT

        # Count entities in query
        from services.search.fts_query_builder import _extract_entities
        entities = _extract_entities(query)
        n_entities = len(entities)

        # Query length (words)
        n_words = len(query.split())

        # Entity density: entities per word
        entity_density = n_entities / max(n_words, 1)

        # Base weights
        vec_w = DEFAULT_VECTOR_WEIGHT
        fts_w = DEFAULT_FTS_WEIGHT

        # Boost FTS for entity-heavy queries (cap at +1.0)
        fts_boost = min(n_entities * ENTITY_FTS_WEIGHT_BOOST, 1.0)
        fts_w += fts_boost

        # Boost vector for long natural-language queries (low entity density)
        if n_words > 6 and entity_density < 0.15:
            vec_w += 0.3

        # Log diagnostics
        if self.diagnostics.enabled:
            self.diagnostics.log("dynamic_weights", "entities", entities)
            self.diagnostics.log("dynamic_weights", "entity_count", n_entities)
            self.diagnostics.log("dynamic_weights", "query_words", n_words)
            self.diagnostics.log("dynamic_weights", "entity_density", round(entity_density, 3))
            self.diagnostics.log("dynamic_weights", "vector_weight", round(vec_w, 2))
            self.diagnostics.log("dynamic_weights", "fts_weight", round(fts_w, 2))

        return vec_w, fts_w

    def rrf_fuse(self, vector_results: List[Dict],
                 fts_results: List[Dict],
                 top_k: int = FINAL_TOP_K,
                 vector_weight: float = 1.0,
                 fts_weight: float = 1.0) -> List[Dict]:
        """Reciprocal Rank Fusion of vector and FTS results.

        V25.19: supports per-channel weights (vector_weight, fts_weight).
        """
        scores = {}
        details = {}

        # Add vector results (rank-based, weighted)
        for rank, hit in enumerate(vector_results):
            pid = hit["para_id"]
            rrf_score = vector_weight / (RRF_K + rank + 1)
            scores[pid] = scores.get(pid, 0) + rrf_score
            details[pid] = {**hit, "vector_rank": rank + 1, "vector_score": hit["score"]}

        # Add FTS results (weighted)
        for rank, hit in enumerate(fts_results):
            pid = hit["para_id"]
            rrf_score = fts_weight / (RRF_K + rank + 1)
            scores[pid] = scores.get(pid, 0) + rrf_score
            if pid in details:
                details[pid] = {**details[pid], "fts_rank": rank + 1, "fts_score": hit["score"]}
            else:
                details[pid] = {**hit, "fts_rank": rank + 1, "fts_score": hit["score"]}

        # Sort by RRF score
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

        results = []
        for pid, rrf_score in ranked:
            d = details[pid]
            d["rrf_score"] = rrf_score
            results.append(d)

        return results

    def rrf_fuse_multi(self, result_lists: List[List[Dict]],
                        top_k: int = FINAL_TOP_K) -> List[Dict]:
        """
        RRF fusion across an arbitrary number of ranked result lists.
        Each list contributes 1/(RRF_K + rank + 1) per para_id; lists that
        agree on a paragraph stack their scores. Used for multi-query fusion
        where each query variant produces a vector list and an FTS list.
        """
        scores = {}
        details = {}
        for rlist in result_lists:
            for rank, hit in enumerate(rlist):
                pid = hit["para_id"]
                rrf_score = 1.0 / (RRF_K + rank + 1)
                scores[pid] = scores.get(pid, 0) + rrf_score
                if pid not in details:
                    details[pid] = {**hit}
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
        results = []
        for pid, rrf_score in ranked:
            d = details[pid]
            d["rrf_score"] = rrf_score
            results.append(d)
        return results

    def _retrieve_candidates(self, query: str, top_k: int,
                              paper_id: Optional[str],
                              expand_queries: bool,
                              filters: Optional[Dict] = None
                              ) -> Tuple[List[Dict], int, int]:
        """
        Retrieve and RRF-fuse candidates. Returns (fused_results, n_variants, n_lists).

        - Single-query path: vector + FTS, fused with rrf_fuse (V25.19: dynamic weights).
        - Multi-query path:  each variant produces vector + FTS lists; an
          optional HyDE paragraph adds one more vector list; all are fused
          with rrf_fuse_multi.
        V24.2: filters (section_l1/year_min/year_max/journal) applied to both channels.
        V25.19: dynamic RRF weights based on query entity density.
        """
        # V25.19: compute dynamic weights for single-query path
        vec_w, fts_w = self._compute_dynamic_weights(query)

        if expand_queries:
            variants = self.query_expander.expand(query)
            if self.diagnostics.enabled:
                self.diagnostics.log("query_expander", "variants", variants)
            all_lists: List[List[Dict]] = []
            for v in variants:
                all_lists.append(self.vector_search(v, top_k, paper_id, filters))
                all_lists.append(self.fts_search(v, top_k, paper_id, filters))
            # Optional HyDE (vector-only channel; skipped if no LLM configured)
            hyde_text = self.query_expander.hyde(query)
            if hyde_text:
                all_lists.append(self.vector_search(hyde_text, top_k, paper_id, filters))
            fused = self.rrf_fuse_multi(all_lists, top_k)
            fused = self._apply_near_dup_suppression(fused)
            return fused, len(variants), len(all_lists)

        vector_results = self.vector_search(query, top_k, paper_id, filters)
        fts_results = self.fts_search(query, top_k, paper_id, filters)

        # Log diagnostics for raw results
        if self.diagnostics.enabled:
            self.diagnostics.set_result("vector_search", vector_results)
            self.diagnostics.set_result("fts_search", fts_results)
            self.diagnostics.log_rrf_details(vector_results, fts_results, [])

        fused = self.rrf_fuse(vector_results, fts_results, top_k,
                               vector_weight=vec_w, fts_weight=fts_w)
        fused = self._apply_near_dup_suppression(fused)
        return fused, 1, 2

    def _apply_near_dup_suppression(self, fused: List[Dict]) -> List[Dict]:
        """Optional near-duplicate suppression; disabled by default.

        Set SCIPAL_NEAR_DUP_THRESHOLD (e.g. 0.90) to enable. Exact duplicates
        are removed by the utility even when the threshold is 0.
        """
        if not os.environ.get("SCIPAL_NEAR_DUP_THRESHOLD", "").strip():
            return fused
        threshold = threshold_from_env(0.0)
        if not fused:
            return fused
        return suppress_near_duplicates(fused, threshold=threshold, score_key="rrf_score")

    def search(self, query: str, top_k: int = FINAL_TOP_K,
               paper_id: str = None, rerank: bool = False,
               expand_queries: bool = MULTI_QUERY,
               filters: Optional[Dict] = None,
               diversify: bool = MMR_DIVERSIFY) -> Dict:
        """
        Hybrid search: vector + FTS + RRF.

        Args:
            expand_queries: if True (default), generate 2-4 query variants
                and fuse all results with RRF (V22.1). Set False to use only
                the original query.
            rerank: if True, apply cross-encoder reranking on a larger
                candidate pool and return top_k precision-ranked results.
            filters: V24.2 metadata filters dict:
                {section_l1, year_min, year_max, journal}
            diversify: V25.19, if True apply MMR diversification after rerank
                to reduce redundant paragraphs from the same paper/section.
        """
        # V25.19: start diagnostics
        if self.diagnostics.enabled:
            self.diagnostics.start(query)

        if rerank:
            candidate_k = max(top_k * 4, 20)
            fused, n_variants, n_lists = self._retrieve_candidates(
                query, candidate_k, paper_id, expand_queries, filters)

            from services.search.reranker import Reranker
            if not hasattr(self, "_reranker"):
                self._reranker = Reranker()

            # V25.19: log pre-rerank state
            if self.diagnostics.enabled:
                self.diagnostics.set_result("rrf_fused", fused, score_key="rrf_score")

            # V25.21: rerank 保留 3 倍候选，让 MMR 有足够池做多样性选择
            rerank_k = min(top_k * 3, len(fused)) if fused else top_k

            final = self._reranker.rerank(query, fused, rerank_k)

            # V25.19: log rerank comparison
            if self.diagnostics.enabled:
                self.diagnostics.log_rerank_comparison(fused, final)
                self.diagnostics.set_result("reranked", final, score_key="rerank_score")

            # V25.19: MMR diversification
            # V25.21: 条件改为 > top_k（现在有更多候选，MMR 从中选 top_k）
            if diversify and hasattr(self, "mmr") and len(final) > top_k:
                before_mmr = list(final)
                if self.diagnostics.enabled:
                    final, mmr_diag = self.mmr.diversify_with_diagnostics(
                        final, top_k=top_k, score_key="rerank_score")
                    self.diagnostics.log("mmr", "diagnostics", mmr_diag)
                    self.diagnostics.log_rerank_comparison(
                        before_mmr, final,
                        score_key_before="rerank_score",
                        score_key_after="rerank_score")
                else:
                    final = self.mmr.diversify(final, top_k=top_k,
                                                 score_key="rerank_score")

            result = {
                "query": query,
                "variants": n_variants,
                "retrieval_lists": n_lists,
                "candidates": len(fused),
                "reranked": True,
                "diversified": diversify and hasattr(self, "mmr"),
                "results": final,
            }

            # V25.19: finish diagnostics
            if self.diagnostics.enabled:
                result["diagnostics"] = self.diagnostics.finish(
                    {"final_count": len(final)})

            return result

        fused, n_variants, n_lists = self._retrieve_candidates(
            query, top_k, paper_id, expand_queries, filters)

        # V25.19: MMR diversification (no rerank path)
        if diversify and hasattr(self, "mmr") and len(fused) > top_k // 2:
            if self.diagnostics.enabled:
                fused, mmr_diag = self.mmr.diversify_with_diagnostics(
                    fused, top_k=top_k, score_key="rrf_score")
                self.diagnostics.log("mmr", "diagnostics", mmr_diag)
            else:
                fused = self.mmr.diversify(fused, top_k=top_k,
                                             score_key="rrf_score")

        result = {
            "query": query,
            "variants": n_variants,
            "retrieval_lists": n_lists,
            "reranked": False,
            "diversified": diversify and hasattr(self, "mmr"),
            "results": fused,
        }

        # V25.19: finish diagnostics
        if self.diagnostics.enabled:
            result["diagnostics"] = self.diagnostics.finish(
                {"final_count": len(fused)})

        return result

    def search_papers(self, query: str, top_k: int = 5) -> List[Dict]:
        """Search across papers by title/abstract."""
        if self.paper_collection is None:
            # paragraph-only index (e.g. rebuilt without the side collections):
            # aggregate paper ids from paragraph hits instead of returning [].
            return self._papers_from_paragraphs(query, top_k)
        # Vector search on papers
        query_emb = self.model.encode([query]).tolist()
        results = self.paper_collection.query(
            query_embeddings=query_emb,
            n_results=top_k
        )

        hits = []
        for i in range(len(results["ids"][0])):
            paper_id = results["ids"][0][i]
            # Get full paper info
            paper = self.conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if paper:
                hits.append({
                    "paper_id": paper_id,
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "journal": paper["journal"],
                    "year": paper["year"],
                    "score": 1.0 - results["distances"][0][i],
                })
        return hits

    def _papers_from_paragraphs(self, query: str, top_k: int) -> List[Dict]:
        """Fallback: rank papers by their best paragraph hit."""
        best: dict[str, float] = {}
        hits = []
        try:
            hits.extend(self.vector_search(query, top_k=max(top_k * 4, 20)))
            hits.extend(self.fts_search(query, top_k=max(top_k * 4, 20)))
        except Exception:  # noqa: BLE001 - fallback must not raise
            return []
        for hit in hits:
            paper_id = hit.get("paper_id")
            score = float(hit.get("score") or 0.0)
            if paper_id and score > best.get(paper_id, 0.0):
                best[paper_id] = score
        results = []
        for paper_id, score in sorted(best.items(), key=lambda item: item[1], reverse=True)[:top_k]:
            paper = self.conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if paper:
                results.append(
                    {
                        "paper_id": paper_id,
                        "title": paper["title"],
                        "authors": paper["authors"],
                        "journal": paper["journal"],
                        "year": paper["year"],
                        "score": score,
                    }
                )
        return results

    def search_figures(self, query: str, top_k: int = 5,
                       paper_id: str = None) -> List[Dict]:
        """Semantic search over figure captions."""
        if not self.fig_collection:
            return []
        query_emb = self.model.encode([query]).tolist()
        where = {"paper_id": paper_id} if paper_id else None
        results = self.fig_collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            where=where
        )
        hits = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            hits.append({
                "fig_id": results["ids"][0][i],
                "caption": results["documents"][0][i],
                "paper_id": meta.get("paper_id"),
                "fig_number": meta.get("fig_number"),
                "file_path": meta.get("file_path"),
                "page": meta.get("page"),
                "score": 1.0 - results["distances"][0][i],
            })
        return hits

    def search_chunks(self, query: str, top_k: int = 10,
                      paper_id: str = None) -> List[Dict]:
        """
        Semantic search over 800-token chunks (V24.1).
        Chunks are larger, context-rich units that improve recall for
        queries needing broader context than a single paragraph.
        Returns chunk hits with source paragraph IDs for back-reference.
        """
        if not self.chunk_collection:
            return []
        query_emb = self.model.encode([query]).tolist()
        where = {"paper_id": paper_id} if paper_id else None
        results = self.chunk_collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            where=where
        )
        hits = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            chunk_id = results["ids"][0][i]
            # Look up source paragraph IDs from SQLite
            para_ids = []
            try:
                row = self.conn.execute(
                    "SELECT start_para_id, end_para_id FROM chunks WHERE chunk_id = ?",
                    (chunk_id,)
                ).fetchone()
                if row:
                    # Fetch all paragraphs between start and end sequence
                    paras = self.conn.execute("""
                        SELECT para_id FROM paragraphs
                        WHERE paper_id = ? AND sequence >= ? AND sequence <= ?
                        ORDER BY sequence
                    """, (meta.get("paper_id"),
                          meta.get("start_sequence", 0),
                          meta.get("end_sequence", 0))).fetchall()
                    para_ids = [p["para_id"] for p in paras]
            except Exception:
                pass
            hits.append({
                "chunk_id": chunk_id,
                "text": results["documents"][0][i],
                "paper_id": meta.get("paper_id"),
                "section_l1": meta.get("section_l1"),
                "section_l2": meta.get("section_l2"),
                "page": meta.get("page"),
                "token_count": meta.get("token_count"),
                "para_ids": para_ids,
                "score": 1.0 - results["distances"][0][i],
            })
        return hits

    def search_tables(self, query: str, top_k: int = 5,
                      paper_id: str = None) -> List[Dict]:
        """Semantic search over table captions and content."""
        if not self.table_collection:
            return []
        query_emb = self.model.encode([query]).tolist()
        where = {"paper_id": paper_id} if paper_id else None
        results = self.table_collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            where=where
        )
        hits = []
        for i in range(len(results["ids"][0])):
            meta = results["metadatas"][0][i]
            hits.append({
                "table_id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "paper_id": meta.get("paper_id"),
                "table_number": meta.get("table_number"),
                "page": meta.get("page"),
                "score": 1.0 - results["distances"][0][i],
            })
        return hits


if __name__ == "__main__":
    searcher = HybridSearch()

    print("=" * 60)
    print("🧪 Hybrid Search Test (V22.1 multi-query)")
    print("=" * 60)

    query = "How does STAT1 regulate immune response?"
    print(f"\nQuery: {query}")
    variants = searcher.query_expander.expand(query)
    print(f"Variants ({len(variants)}):")
    for i, v in enumerate(variants):
        print(f"  [{i+1}] {v}")

    results = searcher.search(query, top_k=5)

    print(f"\nRetrieval lists fused: {results['retrieval_lists']} "
          f"({results['variants']} variants × 2 channels)")
    print(f"\nTop {len(results['results'])} results:\n")

    for i, r in enumerate(results["results"]):
        text_preview = r["text"][:150].replace("\n", " ")
        print(f"  [{i+1}] RRF={r['rrf_score']:.4f}")
        print(f"      {text_preview}...\n")
