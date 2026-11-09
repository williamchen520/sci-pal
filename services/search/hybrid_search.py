"""
Hybrid search: vector + full-text with RRF fusion.
V21.0 - Retrieval layer
V22.1 - Multi-query expansion + optional HyDE
V25.19 - Enhanced FTS query + dynamic RRF weights + MMR diversification + diagnostics
"""
import os
from typing import List, Dict, Tuple, Optional, Callable

from services.search.reference_filter import is_reference_entry
from services.search.boilerplate_filter import clean_boilerplate
from services.search.query_expander import QueryExpander
from services.search.fts_query_builder import FTSQueryBuilder
from services.search.mmr_diversifier import MMRDiversifier
from services.search.retrieval_diagnostics import RetrievalDiagnostics
from services.search.dedup import suppress_near_duplicates, threshold_from_env

from config.paths import EMBEDDING_MODEL
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
def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def _env_int(name: str, default: int, *, low: int, high: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


MULTI_QUERY = _env_flag("SCIPAL_MULTI_QUERY", True)
MAX_QUERY_VARIANTS = _env_int("SCIPAL_MAX_QUERY_VARIANTS", 4, low=1, high=4)

# V25.19: Enhanced FTS query (phrase matching + NEAR + entity weighting)
ENHANCED_FTS = True

# V25.19: Dynamic RRF weights — adjust vector/FTS balance based on query type.
# Entity-heavy queries (lots of gene/protein symbols) get higher FTS weight.
# Natural-language queries get higher vector weight.
DYNAMIC_RRF_WEIGHTS = os.environ.get("SCIPAL_DYNAMIC_RRF_WEIGHTS", "1").strip().lower() not in {"0", "false", "off", "no"}
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
        self._pg_retriever = None

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

        if os.environ.get("SCIPAL_SEARCH_META_BACKEND", "").strip().lower() in {
            "postgres", "postgresql", "pg", "1", "true"
        }:
            from services.db.pg_pool import pg_connection

            pg = pg_connection()
            try:
                clauses = ["duplicate_of IS NULL"]
                params = []
                if year_min is not None:
                    clauses.append("year >= %s")
                    params.append(year_min)
                if year_max is not None:
                    clauses.append("year <= %s")
                    params.append(year_max)
                if journal:
                    clauses.append("lower(journal) LIKE lower(%s)")
                    params.append(f"%{journal}%")
                where = " AND ".join(clauses)
                rows = pg.execute(
                    f"SELECT paper_id FROM papers WHERE {where}", params
                ).fetchall()
                result = [r["paper_id"] for r in rows]
            finally:
                pg.close()
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
        trace_path = os.environ.get("SCIPAL_VECTOR_TRACE_PATH", "").strip()

        def _trace(event, **fields):
            if not trace_path:
                return
            import json as _json
            import time as _time
            try:
                with open(trace_path, "a", encoding="utf-8") as fh:
                    fh.write(_json.dumps({"ts": _time.time(), "event": event, **fields}, ensure_ascii=False) + "\n")
            except OSError:
                pass

        backend = os.environ.get("SCIPAL_VECTOR_BACKEND", "").strip().lower()
        _trace("vector_enter", backend=backend, top_k=top_k, paper_id=paper_id or "", filters=filters or {})
        if os.environ.get("SCIPAL_VECTOR_ENABLED", "1").strip().lower() in {"0", "false", "off", "no"}:
            _trace("vector_disabled")
            return []
        section_filter = (filters or {}).get("section_l1")
        fetch_k = min(top_k * 4, 200) if (EXCLUDE_REFERENCE_ENTRIES or section_filter) else top_k
        if backend in {"pgvector", "pg_vec", "postgres"}:
            if getattr(self, "_pg_vector", None) is None:
                from services.search.pg_vector import PGVectorParagraphSearch

                self._pg_vector = PGVectorParagraphSearch()
            query_emb = self.model.encode([query], normalize_embeddings=True)[0]
            pg_hits = self._pg_vector.search(query_emb, top_k=fetch_k, paper_id=paper_id or "")
            ids = [hit.para_id for hit in pg_hits]
            _trace("vector_pg", count=len(ids), ids=ids[:50])
            allowed = self._get_filtered_paper_ids(filters)
            if allowed is not None:
                pg_hits = [hit for hit in pg_hits if hit.paper_id in set(allowed)]
            hits = []
            for hit in pg_hits:
                if filters and (filters.get("section_l1") or ""):
                    if hit.section_level1 != filters.get("section_l1"):
                        continue
                if EXCLUDE_REFERENCE_ENTRIES and is_reference_entry(
                    hit.text, hit.section_level1, hit.section_level2
                ):
                    continue
                text = clean_boilerplate(hit.text) if CLEAN_BOILERPLATE else hit.text
                if not text:
                    continue
                hits.append({
                    "para_id": hit.para_id,
                    "paper_id": hit.paper_id,
                    "section_l1": hit.section_level1,
                    "section_l2": hit.section_level2,
                    "text": text,
                    "metadata": {
                        "paper_id": hit.paper_id,
                        "section_l1": hit.section_level1,
                        "section_l2": hit.section_level2,
                    },
                    "score": float(hit.rank),
                })
                if len(hits) >= top_k:
                    break
            _trace("vector_pg_out", count=len(hits), ids=[hit["para_id"] for hit in hits])
            return hits

        return []

    def _paradedb_fts_search(self, query: str, top_k: int, paper_id: str, filters: Optional[Dict]):
        """BM25 candidates from ParadeDB; None means fall back to SQLite."""
        if filters and any(filters.get(key) for key in ("year_min", "year_max", "journal")):
            return None
        try:
            import logging

            if getattr(self, "_paradedb_paragraph_fts", None) is None:
                from services.search.pg_fts import ParadeDBParagraphFTS

                self._paradedb_paragraph_fts = ParadeDBParagraphFTS()
            hits = self._paradedb_paragraph_fts.search(
                query,
                top_k=top_k,
                paper_id=paper_id or "",
                section_level1=(filters or {}).get("section_l1") or "",
            )
            paper_ids = (filters or {}).get("paper_ids")
            if paper_ids is not None:
                allowed = set(paper_ids)
                hits = [hit for hit in hits if hit.paper_id in allowed]
            if not hits:
                return None
            return [
                {
                    "para_id": hit.para_id,
                    "paper_id": hit.paper_id,
                    "section_l1": hit.section_level1,
                    "section_l2": hit.section_level2,
                    "text": hit.text,
                    "score": float(hit.rank),
                }
                for hit in hits
            ]
        except Exception as exc:  # noqa: BLE001 - optional backend
            logging.getLogger(__name__).warning(
                "ParadeDB FTS failed, falling back to SQLite: %s", exc
            )
            return None

    def _pg_fts_search(self, query: str, top_k: int, paper_id: str, filters: Optional[Dict]):
        """PG term3 candidates + rerank; None means fall back to SQLite."""
        if filters and any(filters.get(key) for key in ("year_min", "year_max", "journal")):
            return None
        try:
            import logging

            if self._pg_retriever is None:
                from services.search.pg_paragraph_retriever import PGParagraphRetriever

                self._pg_retriever = PGParagraphRetriever()
            result = self._pg_retriever.search(
                query,
                top_k=top_k,
                paper_id=paper_id or "",
                section_l1=(filters or {}).get("section_l1") or "",
            )
            paper_ids = (filters or {}).get("paper_ids")
            if paper_ids is not None:
                allowed = set(paper_ids)
                result = [row for row in result if row["paper_id"] in allowed]
            if not result:
                return None
            return result
        except Exception as exc:  # noqa: BLE001 - PG is optional; SQLite fallback
            logging.getLogger(__name__).warning("PG FTS failed, falling back to SQLite: %s", exc)
            return None

    def fts_search(self, query: str, top_k: int = FTS_TOP_K,
                   paper_id: str = None,
                   filters: Optional[Dict] = None) -> List[Dict]:
        """Full-text search via SQLite FTS5.

        V24.2: filters dict supports section_l1, year_min, year_max, journal.
        Year/journal filters require a JOIN with the papers table.
        V25.19: enhanced FTS query with phrase matching, NEAR, entity weighting.
        """
        backend = os.environ.get("SCIPAL_FTS_BACKEND", "").strip().lower()
        try:
            parade_percent = max(
                0, min(100, int(os.environ.get("SCIPAL_FTS_PARADEDB_PERCENT", "0") or 0))
            )
        except ValueError:
            parade_percent = 0
        if parade_percent:
            import zlib

            use_parade = zlib.crc32(query.encode("utf-8")) % 100 < parade_percent
        else:
            use_parade = False
        if backend in {"paradedb", "parade", "pg_search"} or use_parade:
            parade_results = self._paradedb_fts_search(query, top_k, paper_id, filters)
            if parade_results is not None:
                return parade_results
        if backend in {"postgres", "postgresql", "pg"}:
            pg_results = self._pg_fts_search(query, top_k, paper_id, filters)
            if pg_results is not None:
                return pg_results
        return []

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

    def _paper_row(self, paper_id: str):
        from services.db.pg_pool import pg_connection

        pg = pg_connection()
        try:
            return pg.execute(
                "SELECT * FROM papers WHERE paper_id = %s", (paper_id,)
            ).fetchone()
        finally:
            pg.close()

    def search_papers(self, query: str, top_k: int = 5) -> List[Dict]:
        return self._papers_from_paragraphs(query, top_k)

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
            paper = self._paper_row(paper_id)
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

    def search_figures(self, query: str, top_k: int = 5, paper_id: str = None) -> List[Dict]:
        return []

    def search_chunks(self, query: str, top_k: int = 10, paper_id: str = None) -> List[Dict]:
        return []

    def search_tables(self, query: str, top_k: int = 5, paper_id: str = None) -> List[Dict]:
        return []


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
