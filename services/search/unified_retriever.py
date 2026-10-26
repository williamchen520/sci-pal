"""
Unified retrieval: one query -> evidence envelope for the AI.
V23.1 - Unified envelope + small-to-big + graph expansion
V25.19 - Retrieval diagnostics support

Combines paragraph hybrid search (+rerank), figure search, table search,
paper search, and graph traversal into one structured envelope.
Paragraph hits are precise at the chunk level but are expanded to their
parent section (small-to-big). Paper hits are expanded via CITES/SIMILAR
graph edges to find related papers vector search might miss.
"""
from typing import Dict, List, Optional
import time
from services.search.hybrid_search import HybridSearch
from services.search.shared import get_shared_hybrid
from services.search.reranker import Reranker
from services.search.query_router import QueryRouter
from services.search.context_expander import ContextExpander, HIT_START, HIT_END
from services.search.graph_traverser import GraphTraverser
from services.search.retrieval_diagnostics import RetrievalDiagnostics
from services.search.abstract_search import AbstractSearch  # V30.0: 摘要库检索


class UnifiedRetriever:
    def __init__(self, rerank: bool = True, routing: bool = True,
                 expand: bool = True, graph_expand: bool = True,
                 use_chunks: bool = True, diagnostics: bool = False,
                 use_abstracts: bool = True):  # V30.0: 是否用摘要库
        self.searcher = get_shared_hybrid(diagnostics=diagnostics)
        self.rerank = rerank
        self.routing = routing
        self.expand = expand
        self.graph_expand = graph_expand
        self.use_chunks = use_chunks
        self.use_abstracts = use_abstracts  # V30.0
        self.router = QueryRouter() if routing else None
        if rerank:
            self.reranker = Reranker()
        if expand:
            self.expander = ContextExpander()
        if graph_expand:
            self.graph = GraphTraverser()
        # V30.0: 摘要库检索
        if use_abstracts:
            try:
                self.abstract_searcher = AbstractSearch()
                print("✅ 摘要库检索已加载")
            except Exception as e:
                print(f"⚠️  摘要库检索加载失败: {e}")
                self.abstract_searcher = None
        else:
            self.abstract_searcher = None
        # V25.19: diagnostics
        self.diagnostics = RetrievalDiagnostics(enabled=diagnostics)

    def retrieve(self, query: str, paper_id: Optional[str] = None,
                 top_paragraphs: int = 6, top_figures: int = 3,
                 top_tables: int = 2, top_papers: int = 3,
                 filters: Optional[Dict] = None) -> Dict:
        """
        Run the needed retrieval channels and assemble an evidence envelope.
        With routing enabled, only channels matching the query intent run.
        Paragraph hits are expanded to parent sections when expand=True.
        V24.2: filters dict {section_l1, year_min, year_max, journal}.
        V25.19: diagnostics capture for every stage.
        V27.2: 打印 reranker 状态和召回数量
        """
        # V27.2: 打印 reranker 状态
        print(f"  🔍 Retrieval: rerank={self.rerank}, top_paragraphs={top_paragraphs}")
        # V25.19: start diagnostics
        if self.diagnostics.enabled:
            self.diagnostics.start(query)

        # Decide which channels to run
        if self.routing:
            route = self.router.route(query, paper_id)
            channels = route["channels"]
            # V25.19: log routing diagnostics
            if self.diagnostics.enabled:
                self.diagnostics.log("query_router", "channels", route["channels"])
                self.diagnostics.log("query_router", "primary", route["primary"])
                self.diagnostics.log("query_router", "scores", route["scores"])
        else:
            route = None
            channels = ["qa", "figure", "table"] + ([] if paper_id else ["papers"])

        # 1. Paragraphs: hybrid recall -> cross-encoder rerank (always)
        paragraphs = []
        if "qa" in channels or "citation" in channels:
            if self.rerank:
                # V27.2: 增加粗召回数量，给 reranker 更多候选
                candidate_k = max(top_paragraphs * 5, 50)

                # V25.19: vector search with diagnostics
                if self.diagnostics.enabled:
                    with self.diagnostics.stage("vector_search"):
                        vector = self.searcher.vector_search(query, candidate_k, paper_id, filters)
                    self.diagnostics.set_result("vector_search", vector)
                else:
                    vector = self.searcher.vector_search(query, candidate_k, paper_id, filters)

                # V25.19: FTS search with diagnostics (capture enhanced query)
                if self.diagnostics.enabled:
                    with self.diagnostics.stage("fts_search"):
                        fts = self.searcher.fts_search(query, candidate_k, paper_id, filters)
                    self.diagnostics.set_result("fts_search", fts)
                    if hasattr(self.searcher, "fts_builder"):
                        fts_info = self.searcher.fts_builder.explain(query)
                        self.diagnostics.log("fts_search", "enhanced_query", fts_info.get("fts_query", ""))
                        self.diagnostics.log("fts_search", "entities", fts_info.get("entities", []))
                else:
                    fts = self.searcher.fts_search(query, candidate_k, paper_id, filters)

                # V25.19: dynamic weights + RRF fuse with diagnostics
                vec_w, fts_w = self.searcher._compute_dynamic_weights(query)
                if self.diagnostics.enabled:
                    with self.diagnostics.stage("rrf_fuse"):
                        fused = self.searcher.rrf_fuse(vector, fts, candidate_k,
                                                        vector_weight=vec_w, fts_weight=fts_w)
                    self.diagnostics.set_result("rrf_fuse", fused, score_key="rrf_score")
                    self.diagnostics.log("rrf_fuse", "vector_weight", vec_w)
                    self.diagnostics.log("rrf_fuse", "fts_weight", fts_w)
                    self.diagnostics.log_rrf_details(vector, fts, fused)
                else:
                    fused = self.searcher.rrf_fuse(vector, fts, candidate_k,
                                                    vector_weight=vec_w, fts_weight=fts_w)

                # V27.5: 实体精确检索 - 确保包含关键实体的段落一定被召回
                _entity_started = time.time()
                from services.search.agentic_search import extract_key_entities
                _ner_started = time.time()
                key_entities = extract_key_entities(query)
                self.diagnostics.mark("entity_ner", (time.time() - _ner_started) * 1000)
                print(f"  🎯 Key entities: {key_entities[:5]}")

                # 对每个实体做一次 FTS 搜索，加到候选池里
                entity_hits = []
                _entity_search_ms = 0.0
                for entity in key_entities[:3]:  # 只搜前 3 个最重要的实体
                    try:
                        _one_started = time.time()
                        entity_results = self.searcher.fts_search(entity, top_k=10, paper_id=paper_id, filters=filters)
                        _entity_search_ms += (time.time() - _one_started) * 1000
                        entity_hits.extend(entity_results)
                        print(f"     → Entity '{entity}': {len(entity_results)} hits")
                    except Exception as e:
                        print(f"     → Entity '{entity}': search failed ({e})")
                self.diagnostics.mark("entity_fts_total", _entity_search_ms)

                # 去重，然后加到 fused 里
                if entity_hits:
                    existing_ids = {p.get("paragraph_id") or p.get("id") for p in fused}
                    new_hits = [p for p in entity_hits if (p.get("paragraph_id") or p.get("id")) not in existing_ids]
                    fused.extend(new_hits)
                    print(f"  📊 Entity boost: total {len(entity_hits)} hits, +{len(new_hits)} new paragraphs added")
                else:
                    print(f"  📊 Entity boost: no new paragraphs found")
                self.diagnostics.mark("entity_boost", (time.time() - _entity_started) * 1000)

                # V27.2: 增加 rerank_k，让 MMR 有更多候选做多样性选择
                rerank_k = min(top_paragraphs * 4, len(fused)) if fused else top_paragraphs

                # V27.2: 打印粗召回和精排数量
                print(f"  📊 Hybrid recall: {len(fused)} candidates -> rerank top {rerank_k}")

                # V25.19: rerank with diagnostics
                if self.diagnostics.enabled:
                    with self.diagnostics.stage("rerank"):
                        paragraphs = self.reranker.rerank(query, fused, rerank_k)
                    self.diagnostics.set_result("rerank", paragraphs, score_key="rerank_score")
                    self.diagnostics.log_rerank_comparison(fused, paragraphs)
                else:
                    paragraphs = self.reranker.rerank(query, fused, rerank_k)

                # V27.2: 打印精排后的数量
                print(f"  ✅ After rerank: {len(paragraphs)} paragraphs")

                # V25.19: MMR diversification with diagnostics
                # V25.21: 条件改为 > top_paragraphs（现在有更多候选，MMR 从中选 top_paragraphs）
                if hasattr(self.searcher, "mmr") and len(paragraphs) > top_paragraphs:
                    # V27.2: 打印 MMR 选择的数量
                    print(f"  🎯 MMR diversity selection: {len(paragraphs)} -> top {top_paragraphs}")
                    if self.diagnostics.enabled:
                        with self.diagnostics.stage("mmr_diversify"):
                            paragraphs, mmr_diag = self.searcher.mmr.diversify_with_diagnostics(
                                paragraphs, top_k=top_paragraphs, score_key="rerank_score")
                        self.diagnostics.set_result("mmr_diversify", paragraphs, score_key="rerank_score")
                        self.diagnostics.log("mmr_diversify", "diagnostics", mmr_diag)
                    else:
                        paragraphs = self.searcher.mmr.diversify(
                            paragraphs, top_k=top_paragraphs, score_key="rerank_score")
            else:
                res = self.searcher.search(query, top_paragraphs, paper_id,
                                            filters=filters)
                paragraphs = res["results"]

        # 1b. Small-to-big: expand precise hits to parent section context
        parent_contexts = []
        _parents_started = time.time()
        if self.expand and paragraphs:
            parent_contexts = self.expander.expand(
                paragraphs, mode="section", max_parents=top_paragraphs
            )
        self.diagnostics.mark("parent_contexts", (time.time() - _parents_started) * 1000)

        # 2. Figures (caption semantics)
        figures = []
        if "figure" in channels:
            figures = self.searcher.search_figures(query, top_figures, paper_id)

        # 3. Tables (caption + content semantics)
        tables = []
        if "table" in channels:
            tables = self.searcher.search_tables(query, top_tables, paper_id)

        # 4. Papers (cross-paper discovery); skip when scoped to one paper
        papers = []
        graph_neighbors = []
        if "papers" in channels and not paper_id:
            papers = self.searcher.search_papers(query, top_papers)

            # 4b. Graph expansion: from vector-retrieved seed papers,
            #     expand via CITES/SIMILAR edges to find related papers.
            if self.graph_expand and papers:
                seed_ids = [p.get("paper_id") for p in papers if p.get("paper_id")]
                if seed_ids:
                    graph_neighbors = self.graph.expand(
                        seed_ids, max_neighbors=max_papers, relation="all"
                    )

        # 5. Chunks (800-token context-rich units, V24.1)
        chunks = []
        if self.use_chunks and ("qa" in channels):
            chunks = self.searcher.search_chunks(query, top_k=top_paragraphs,
                                                   paper_id=paper_id)

        # 6. Abstracts (V30.0): 摘要库检索，跟全文库并列
        abstracts = []
        _abstracts_started = time.time()
        if self.abstract_searcher and not paper_id:  # 不指定单篇论文时才搜摘要库
            try:
                print(f"  📚 Searching abstracts database...")
                abstracts = self.abstract_searcher.search(query, top_k=top_paragraphs)
                print(f"  ✅ Found {len(abstracts)} abstracts")
            except Exception as e:
                print(f"  ⚠️  Abstract search failed: {e}")
                abstracts = []
        self.diagnostics.mark("abstracts", (time.time() - _abstracts_started) * 1000)

        result = {
            "query": query,
            "paper_id": paper_id,
            "route": route,
            "paragraphs": paragraphs,          # precise hits (anchor ids)
            "parent_contexts": parent_contexts,  # expanded section context
            "chunks": chunks,                  # 800-token context units (V24.1)
            "figures": figures,
            "tables": tables,
            "papers": papers,
            "graph_neighbors": graph_neighbors,  # papers found via graph traversal
            "abstracts": abstracts,  # V30.0: 摘要库结果
        }

        # V25.19: finish diagnostics
        if self.diagnostics.enabled:
            result["diagnostics"] = self.diagnostics.finish({
                "paragraphs": len(paragraphs),
                "figures": len(figures),
                "tables": len(tables),
                "papers": len(papers),
                "graph_neighbors": len(graph_neighbors),
                "chunks": len(chunks),
            })
            stages = result["diagnostics"].get("stages") or {}
            result["timings"] = {
                name: info.get("elapsed_ms") for name, info in stages.items()
            }
            result["timings"]["total_ms"] = result["diagnostics"].get("total_time_ms")

        return result

    def get_diagnostics_report(self) -> Optional[Dict]:
        """V25.19: Return the last diagnostics report, or None if disabled."""
        if not self.diagnostics.enabled:
            return None
        return self.diagnostics.stages  # Return captured stages

    def to_envelope(self, query: str, paper_id: Optional[str] = None,
                    **kwargs) -> str:
        """
        Render the retrieval results as a numbered text envelope for the LLM.
        Each evidence item gets a stable ID the model must cite ([P1], [F1]...).
        """
        env = self.retrieve(query, paper_id, **kwargs)
        route_tag = ""
        if env.get("route"):
            route_tag = f" [routed to: {', '.join(env['route']['channels'])}]"
        lines = [f"QUERY: {query}{route_tag}", "=" * 50, "EVIDENCE:"]

        if env["parent_contexts"]:
            lines.append("\n## Relevant text passages (section context; "
                         f"{HIT_START} marks the matched paragraph {HIT_END})")
            for i, pctx in enumerate(env["parent_contexts"], 1):
                sec = pctx.get("section") or ""
                tag = f" ({sec})" if sec else ""
                page = f", p{pctx['page']}" if pctx.get("page") else ""
                lines.append(f"[P{i}]{tag}{page}\n{pctx['text']}")
        elif env["paragraphs"]:
            lines.append("\n## Relevant text passages")
            for i, p in enumerate(env["paragraphs"], 1):
                section = p.get("section_l1") or p.get("metadata", {}).get("section_l1", "")
                tag = f" ({section})" if section else ""
                lines.append(f"[P{i}]{tag}\n{p['text']}")

        if env.get("chunks"):
            lines.append("\n## Context chunks (800-token units)")
            for i, c in enumerate(env["chunks"], 1):
                sec = c.get("section_l1") or ""
                tag = f" ({sec})" if sec else ""
                page = f", p{c['page']}" if c.get("page") else ""
                lines.append(f"[C{i}]{tag}{page} [{c.get('token_count', '?')} tok]\n{c['text'][:1200]}")

        if env["figures"]:
            lines.append("\n## Relevant figures")
            for i, f in enumerate(env["figures"], 1):
                lines.append(
                    f"[F{i}] {f['fig_number']} (page {f['page']}, "
                    f"file: {f['file_path']})\n{f['caption']}"
                )

        if env["tables"]:
            lines.append("\n## Relevant tables")
            for i, t in enumerate(env["tables"], 1):
                lines.append(f"[T{i}] {t['table_number']} (page {t['page']})\n{t['content'][:800]}")

        if env["papers"]:
            lines.append("\n## Related papers")
            for i, p in enumerate(env["papers"], 1):
                lines.append(
                    f"[R{i}] {p['title']} ({p.get('year') or 'n.d.'}). "
                    f"{p.get('journal') or ''}"
                )

        # V30.0: 摘要库结果
        if env.get("abstracts"):
            lines.append("\n## Related abstracts (only abstract, no full text)")
            for i, a in enumerate(env["abstracts"], 1):
                lines.append(
                    f"[A{i}] {a['title']} ({a.get('year') or 'n.d.'}). "
                    f"{a.get('journal') or ''}\n"
                    f"    DOI: {a.get('doi') or 'N/A'}\n"
                    f"    Abstract: {a.get('abstract', '')[:500]}..."
                )

        if env.get("graph_neighbors"):
            lines.append("\n## Graph-related papers (via CITES/SIMILAR)")
            for i, g in enumerate(env["graph_neighbors"], 1):
                rel_tag = "similar" if g["relation"] == "similar" else "cites"
                lines.append(
                    f"[G{i}] ({rel_tag}, conf={g['confidence']:.2f}) "
                    f"{g['title']} ({g.get('year') or 'n.d.'}). "
                    f"{g.get('journal') or ''}"
                )

        lines.append("=" * 50)
        lines.append("Cite evidence using the IDs above (e.g. [P1], [F2]).")
        return "\n".join(lines)


if __name__ == "__main__":
    print("=" * 60)
    print("📨 Unified Retrieval Envelope Test (V23.1)")
    print("=" * 60)

    retriever = UnifiedRetriever(rerank=True, graph_expand=True)

    # Test 1: QA query
    query = "How does STAT1 regulate the interferon immune response?"
    print(f"\n── Test 1: QA query ──")
    print(f"Query: {query}\n")
    envelope = retriever.to_envelope(query)
    print(envelope)

    # Test 2: Papers discovery query (triggers graph expansion)
    query2 = "Which papers study JAK-STAT signaling in cancer?"
    print(f"\n\n── Test 2: Papers discovery + graph expansion ──")
    print(f"Query: {query2}\n")
    result = retriever.retrieve(query2, top_papers=3)
    print(f"  Vector papers: {len(result.get('papers', []))}")
    print(f"  Graph neighbors: {len(result.get('graph_neighbors', []))}")
    for g in result.get("graph_neighbors", []):
        print(f"    [{g['relation']}] {g['title'][:55]} ({g.get('year') or '?'})")
