"""
Sci-Pal API Server — V25.8
Wraps the retrieval layer (hybrid search + rerank + query routing +
context expansion + multi-query + reference/boilerplate filtering +
graph traversal + agentic + chunking + metadata filters + communities)
as a REST API, with a minimal built-in frontend.

Usage:
  python api_server.py
  # then open http://localhost:5000
"""
import os
import sys
import threading
from pathlib import Path
from typing import Optional, Dict
from flask import Flask, jsonify, request, send_from_directory, Response

# Ensure project root is on sys.path for services.* imports
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# V26.3: 导入任务管理器
from services.review.task_manager import task_manager

DB_PATH = PROJECT_ROOT / "data" / "research.db"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DOCUMENTS_DIR = PROJECT_ROOT / "documents"
OUTLINE_DIR = PROJECT_ROOT / "data" / "outlines"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

# Lazy-loaded retrieval components (loaded on first request to keep startup fast)
_retriever = None
_hybrid = None
_graph = None
_review_generator = None
_llm_client = None
_qa_service = None
_hybrid_retriever = None  # V33.1: 混合检索器（本地+在线NCBI/PMC）


def get_qa_service():
    """Lazy-load Q&A service (V26.0: RAG 学术问答)。"""
    global _qa_service
    if _qa_service is None:
        from services.qa.qa_service import QAService
        _qa_service = QAService()
    return _qa_service


def get_llm_client():
    """Lazy-load LLM client (V25.4: 支持 Ollama 和云端 OpenAI 兼容 API)。"""
    global _llm_client
    if _llm_client is None:
        from services.review.llm_client import create_llm_client
        _llm_client = create_llm_client()
    return _llm_client


def get_review_generator():
    """Lazy-load ReviewGenerator (V25.0)."""
    global _review_generator
    if _review_generator is None:
        from services.review.review_generator import ReviewGenerator
        _review_generator = ReviewGenerator(
            llm_client=get_llm_client(),
            retriever=get_retriever(),
            use_llm_verification=False,
            db_path=str(DB_PATH),  # V25.3: 用于大纲生成时复用文献聚类信息
        )
    return _review_generator


_review_store = None


def get_review_store():
    """Lazy-load ReviewStore（V25.6: 综述结果暂存，用于前端点击溯源）。"""
    global _review_store
    if _review_store is None:
        from services.review.review_store import ReviewStore
        _review_store = ReviewStore(ttl_seconds=3600, max_entries=100)
    return _review_store


_outline_store = None


def get_outline_store():
    """Lazy-load OutlineStore（V25.9: 大纲保存/加载，文件级 JSON 存储）。"""
    global _outline_store
    if _outline_store is None:
        from services.review.outline_store import OutlineStore
        _outline_store = OutlineStore(data_dir=str(OUTLINE_DIR))
    return _outline_store


def get_retriever():
    global _retriever
    if _retriever is None:
        # V31.71: 回退到旧的统一检索器（unified_retriever.py），检索层不改，只改数据层
        from services.search.unified_retriever import UnifiedRetriever
        _retriever = UnifiedRetriever(
            rerank=True, routing=True, expand=True, graph_expand=True)
    return _retriever


def get_hybrid_retriever():
    """V33.1: Lazy-load 混合检索器（本地+在线NCBI/PMC）。"""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        from services.search.hybrid_retriever import HybridRetriever
        _hybrid_retriever = HybridRetriever(use_online=True, verbose=True)
    return _hybrid_retriever


def get_graph():
    global _graph
    if _graph is None:
        from services.search.graph_traverser import GraphTraverser
        _graph = GraphTraverser()
    return _graph


def get_hybrid():
    global _hybrid
    if _hybrid is None:
        # V31.71: 回退到旧的混合检索（hybrid_search.py），检索层不改，只改数据层
        from services.search.hybrid_search import HybridSearch
        _hybrid = HybridSearch()
    return _hybrid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_filters(source) -> Optional[Dict]:
    """Parse V24.2 metadata filters from request args or JSON body."""
    filters = {}
    section = source.get("section") or source.get("section_l1")
    if section:
        filters["section_l1"] = section
    year_min = source.get("year_min")
    if year_min is not None and str(year_min).strip():
        try:
            filters["year_min"] = int(year_min)
        except (ValueError, TypeError):
            pass
    year_max = source.get("year_max")
    if year_max is not None and str(year_max).strip():
        try:
            filters["year_max"] = int(year_max)
        except (ValueError, TypeError):
            pass
    journal = source.get("journal")
    if journal:
        filters["journal"] = journal
    return filters if filters else None


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "sci-pal",
        "version": "V25.14",
        "db_exists": DB_PATH.exists(),
    })


# ---------------------------------------------------------------------------
# V33.12: Unified Task API
# ---------------------------------------------------------------------------
@app.route("/api/tasks", methods=["GET"])
def list_unified_tasks():
    """List all tasks with optional filters: type, status, limit."""
    from services.unified_task_manager import list_tasks
    task_type = request.args.get("type")
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    tasks = list_tasks(task_type=task_type, status=status, limit=limit)
    return jsonify({"tasks": tasks, "count": len(tasks)})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_unified_task(task_id):
    """Get task details by ID."""
    from services.unified_task_manager import get_task
    task = get_task(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    return jsonify(task)


@app.route("/api/tasks/<task_id>/events", methods=["GET"])
def task_sse_events(task_id):
    """SSE stream for real-time task progress."""
    from services.unified_task_manager import subscribe
    def generate():
        for event, data in subscribe(task_id):
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/retrieve", methods=["GET", "POST"])
def retrieve():
    """
    Unified retrieval endpoint.

    Query params (GET) or JSON body (POST):
      q:        search query (required)
      top_k:    number of evidence passages to return (default 6)
      paper_id: restrict to a single paper (optional)
      route:    force query route ('qa'|'citation'|'figure'|'method'|'auto')
      section:  filter by section_level1 (e.g. 'Methods', 'Introduction') [V24.2]
      year_min: minimum publication year [V24.2]
      year_max: maximum publication year [V24.2]
      journal:  filter by journal name (partial match) [V24.2]
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = data.get("q", "").strip()
        top_paragraphs = int(data.get("top_paragraphs", 6))
        top_figures = int(data.get("top_figures", 3))
        paper_id = data.get("paper_id") or None
        filters = _parse_filters(data)
    else:
        q = request.args.get("q", "").strip()
        top_paragraphs = int(request.args.get("top_paragraphs", 6))
        top_figures = int(request.args.get("top_figures", 3))
        paper_id = request.args.get("paper_id") or None
        filters = _parse_filters(request.args)

    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    try:
        retriever = get_retriever()
        # V33.10 fix: UnifiedRetriever 的方法是 retrieve()，不是 search_papers()
        # search_papers 是 HybridRetriever 的方法（用于 /api/search/hybrid）
        result = retriever.retrieve(
            query=q,
            paper_id=paper_id,
            top_paragraphs=top_paragraphs,
            top_figures=top_figures,
            filters=filters,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Retrieval failed: {str(e)}"}), 500


# ============================================================
# V26.0: RAG Q&A 问答 API
# ============================================================

@app.route("/api/qa/ask", methods=["POST"])
def qa_ask():
    """
    RAG 学术问答接口（V26.0）。

    POST JSON body:
      question:    用户问题（required）
      paper_id:    限定在某篇论文内检索（optional）
      diagnostics: 是否返回检索诊断信息（default false）
    """
    data = request.get_json(silent=True) or {}
    question = data.get("question", "").strip()
    paper_id = data.get("paper_id") or None
    include_diagnostics = bool(data.get("diagnostics", False))

    if not question:
        return jsonify({"error": "参数 'question' 不能为空"}), 400

    try:
        qa = get_qa_service()
        result = qa.ask(
            question=question,
            paper_id=paper_id,
            include_diagnostics=include_diagnostics,
        )
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR] Q&A failed: {e}")
        return jsonify({"error": f"问答失败: {str(e)}"}), 500


@app.route("/api/qa/status", methods=["GET"])
def qa_status():
    """
    检查 LLM 服务状态（V26.0）。

    返回 LLM 提供商、模型、是否可用、可用模型列表。
    """
    try:
        qa = get_qa_service()
        status = qa.get_llm_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"available": False, "error": str(e)}), 500


@app.route("/api/agentic/search", methods=["GET", "POST"])
def agentic_search():
    """
    Agentic multi-hop search endpoint.

    Query params (GET) or JSON body (POST):
      q:             search query (required)
      max_hops:      max iterative hops (default 3, max 5)
      min_coverage:  stop when entity coverage >= this (default 0.6)
      top_paragraphs: paragraphs per hop (default 6)
      paper_id:      restrict to a single paper (optional)
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        q = data.get("q", "").strip()
        max_hops = min(int(data.get("max_hops", 3)), 5)
        min_coverage = float(data.get("min_coverage", 0.6))
        top_paragraphs = int(data.get("top_paragraphs", 6))
        paper_id = data.get("paper_id") or None
    else:
        q = request.args.get("q", "").strip()
        max_hops = min(int(request.args.get("max_hops", 3)), 5)
        min_coverage = float(request.args.get("min_coverage", 0.6))
        top_paragraphs = int(request.args.get("top_paragraphs", 6))
        paper_id = request.args.get("paper_id") or None

    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    try:
        from services.search.agentic_search import AgenticSearcher
        agentic = AgenticSearcher(
            max_hops=max_hops, min_coverage=min_coverage)
        result = agentic.search(
            q, paper_id=paper_id, top_paragraphs=top_paragraphs)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Agentic search failed: {str(e)}"}), 500


@app.route("/api/papers", methods=["GET"])
def list_papers():
    """List all papers with basic metadata."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT paper_id, title, authors, journal, year, doi,
               total_paragraphs, total_figures, total_tables
        FROM papers ORDER BY year DESC, title
    """).fetchall()
    conn.close()
    return jsonify({"count": len(rows), "papers": [dict(r) for r in rows]})


@app.route("/api/papers/<paper_id>", methods=["GET"])
def paper_detail(paper_id):
    """Get detailed metadata for a single paper."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    paper = conn.execute(
        "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    if not paper:
        conn.close()
        return jsonify({"error": "Paper not found"}), 404

    # Citation graph neighbors
    cites = conn.execute("""
        SELECT p.paper_id, p.title, p.year, c.confidence
        FROM cross_paper_index c
        JOIN papers p ON p.paper_id = c.target_paper_id
        WHERE c.source_paper_id = ? AND c.relation = 'cites'
        ORDER BY c.confidence DESC
    """, (paper_id,)).fetchall()
    cited_by = conn.execute("""
        SELECT p.paper_id, p.title, p.year, c.confidence
        FROM cross_paper_index c
        JOIN papers p ON p.paper_id = c.source_paper_id
        WHERE c.target_paper_id = ? AND c.relation = 'cites'
        ORDER BY c.confidence DESC
    """, (paper_id,)).fetchall()
    similar = conn.execute("""
        SELECT p.paper_id, p.title, p.year, c.confidence
        FROM cross_paper_index c
        JOIN papers p ON p.paper_id = c.target_paper_id
        WHERE c.source_paper_id = ? AND c.relation = 'similar'
        ORDER BY c.confidence DESC LIMIT 10
    """, (paper_id,)).fetchall()
    conn.close()

    return jsonify({
        "paper": dict(paper),
        "cites": [dict(r) for r in cites],
        "cited_by": [dict(r) for r in cited_by],
        "similar": [dict(r) for r in similar],
    })


@app.route("/api/papers/<paper_id>/graph", methods=["GET"])
def paper_graph(paper_id):
    """
    Graph traversal from a paper.

    Query params:
      relation: 'cites' | 'similar' | 'all' (default 'all')
      direction: 'out' | 'in' | 'both' (default 'both')
      max_hops: BFS depth (default 1, max 3)
      max_total: max papers to return (default 10)
    """
    relation = request.args.get("relation", "all")
    direction = request.args.get("direction", "both")
    max_hops = min(int(request.args.get("max_hops", 1)), 3)
    max_total = int(request.args.get("max_total", 10))

    try:
        graph = get_graph()
        if max_hops <= 1:
            neighbors = graph.get_neighbors(
                [paper_id], relation=relation, direction=direction)
            neighbors = neighbors[:max_total]
        else:
            neighbors = graph.traverse(
                [paper_id], max_hops=max_hops, max_total=max_total,
                relation=relation)
        return jsonify({
            "paper_id": paper_id,
            "relation": relation,
            "max_hops": max_hops,
            "count": len(neighbors),
            "neighbors": neighbors,
        })
    except Exception as e:
        return jsonify({"error": f"Graph traversal failed: {str(e)}"}), 500


@app.route("/api/graph/stats", methods=["GET"])
def graph_stats():
    """Return graph statistics (nodes, edges, components, top-cited)."""
    try:
        graph = get_graph()
        return jsonify(graph.stats())
    except Exception as e:
        return jsonify({"error": f"Graph stats failed: {str(e)}"}), 500


@app.route("/api/communities", methods=["GET"])
def list_communities():
    """
    List paper communities (V24.3).

    Query params:
      min_size:  minimum community size (default 1)
      detailed:  if '1', include member paper list per community
    """
    import sqlite3
    min_size = int(request.args.get("min_size", 1))
    detailed = request.args.get("detailed", "0") == "1"

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        comms = conn.execute("""
            SELECT c.community_id, c.size, c.representative_paper_id,
                   c.summary, c.keywords, c.avg_year,
                   p.title as rep_title, p.authors as rep_authors,
                   p.journal as rep_journal, p.year as rep_year
            FROM paper_communities c
            LEFT JOIN papers p ON c.representative_paper_id = p.paper_id
            WHERE c.size >= ?
            ORDER BY c.size DESC
        """, (min_size,)).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return jsonify({
            "error": "Communities not built yet. Run: python -m build_db.build_communities --apply"
        }), 404

    result = []
    for c in comms:
        item = {
            "community_id": c["community_id"],
            "size": c["size"],
            "representative": {
                "paper_id": c["representative_paper_id"],
                "title": c["rep_title"],
                "authors": c["rep_authors"],
                "journal": c["rep_journal"],
                "year": c["rep_year"],
            },
            "summary": c["summary"],
            "keywords": c["keywords"],
            "avg_year": c["avg_year"],
        }
        if detailed:
            members = conn.execute("""
                SELECT m.paper_id, m.centrality, p.title, p.year, p.journal
                FROM community_members m
                LEFT JOIN papers p ON m.paper_id = p.paper_id
                WHERE m.community_id = ?
                ORDER BY m.centrality DESC
            """, (c["community_id"],)).fetchall()
            item["members"] = [dict(m) for m in members]
        result.append(item)

    conn.close()
    return jsonify({
        "total_communities": len(result),
        "total_papers": sum(c["size"] for c in result),
        "communities": result,
    })


# ---------------------------------------------------------------------------
# V25.0: 综述生成智能体
# ---------------------------------------------------------------------------

@app.route("/api/review/outline", methods=["GET", "POST"])
def generate_outline():
    """
    V26.3: 异步生成段落级大纲（支持取消）

    参数:
      topic: 综述主题（必填）
      max_papers: 最多检索的论文数，默认 20
      review_type: 综述模板类型（narrative/comparative/systematic），默认 narrative

    返回:
      - task_id: 任务ID（前端用这个ID查询任务状态）
    """
    # 支持 JSON body 和 query/form 参数
    json_body = request.get_json(silent=True) or {}
    def get_param(name, default=None):
        if name in json_body:
            return json_body[name]
        return request.values.get(name, default)

    topic = str(get_param("topic", "")).strip()
    if not topic:
        return jsonify({"error": "topic is required"}), 400

    max_papers = int(get_param("max_papers", 20))
    review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
    language = str(get_param("language", "en")).strip().lower() or "en"
    valid_review_types = {"narrative", "comparative", "systematic"}
    if review_type.lower() not in valid_review_types:
        review_type = "narrative"

    # V26.3: 创建任务
    task_id = task_manager.create_task("generate_outline")

    # V26.3: 在后台线程里运行生成大纲的任务
    def run_task():
        try:
            llm = get_llm_client()
            if not llm.is_available():
                task_manager.fail_task(task_id, "LLM not available")
                return

            generator = get_review_generator()
            result = generator.generate_outline(
                topic=topic,
                max_papers=max_papers,
                review_type=review_type,
                language=language,
                task_id=task_id,  # V26.3: 传入 task_id，让生成函数可以检查是否被取消
            )
            task_manager.complete_task(task_id, result)
        except Exception as e:
            # V26.3: 如果是用户主动取消，不要显示错误信息
            if "Task cancelled by user" in str(e):
                print(f"[INFO] Task cancelled by user")
                # V26.4: 立即把任务状态改成 cancelled，这样前端就能看到了
                task_manager.cancel_task(task_id)
            else:
                print(f"[ERROR] Outline generation failed: {e}")
                import traceback
                traceback.print_exc()
                task_manager.fail_task(task_id, str(e))

    # 启动后台线程
    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()

    # V26.3: 立即返回 task_id
    return jsonify({"task_id": task_id})


# V26.5: 查询当前运行中的任务（用于刷新页面后恢复任务）
@app.route("/api/review/running_task", methods=["GET"])
def get_running_task():
    """
    查询当前是否有运行中的任务
    用于刷新页面后恢复任务
    """
    task = task_manager.get_running_task()
    if not task:
        return jsonify({"running": False})
    return jsonify({"running": True, "task": task})


# V26.3: 查询任务状态
@app.route("/api/review/task/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """
    查询任务状态
    返回:
      - status: running / completed / failed / cancelled
      - result: 任务结果（如果完成了）
      - error: 错误信息（如果失败了）
    """
    task = task_manager.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


# V26.3: 取消任务
@app.route("/api/review/cancel/<task_id>", methods=["POST"])
def cancel_task(task_id):
    """
    取消一个正在运行的任务
    """
    success = task_manager.cancel_task(task_id)
    if not success:
        return jsonify({"error": "Task not found or already finished"}), 404
    return jsonify({"success": True, "message": "Task cancelled"})


# ── V26.1: 自动发配论文到章节 ──

@app.route("/api/review/assign_papers", methods=["POST"])
def assign_papers_to_outline_route():
    """V26.1: 自动计算每篇论文与各章节的相似度，把论文发配到相关章节。

    Body:
      outline: 大纲 JSON {"sections": [...]}（必填）
      papers: 论文列表 [{"paper_id": ..., "title": ..., ...}]（必填）
      evidence_cards: 证据卡片列表（可选）

    Returns:
      更新后的大纲（每章节包含 assigned_paper_ids）
    """
    data = request.get_json(silent=True) or {}
    outline = data.get("outline")
    papers = data.get("papers")
    evidence_cards = data.get("evidence_cards", [])

    if not outline or not outline.get("sections"):
        return jsonify({"error": "outline is required"}), 400
    if not papers:
        return jsonify({"error": "papers is required"}), 400

    try:
        from services.review.review_generator import assign_papers_to_outline
        updated_outline = assign_papers_to_outline(outline, papers, evidence_cards)
        return jsonify({"outline": updated_outline})
    except Exception as e:
        print(f"[ERROR] Assign papers failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Assign papers failed: {str(e)}"}), 500


# ── V31.75: 按大纲搜索并分配论文 ──

@app.route("/api/review/search_and_assign", methods=["POST"])
def search_and_assign_route():
    """V31.75: 按大纲内容搜索论文，然后自动分配给对应的章节和段落。

    Body:
      outline: 大纲 JSON {"sections": [...]}（必填）
      topic: 综述主题（必填）
      max_papers: 最大论文数（可选，默认 100）

    Returns:
      outline: 更新后的大纲（每章节包含 assigned_paper_ids）
      papers: 搜索到的论文列表
    """
    data = request.get_json(silent=True) or {}
    outline = data.get("outline")
    topic = data.get("topic", "")
    max_papers = int(data.get("max_papers", 100))

    if not outline or not outline.get("sections"):
        return jsonify({"error": "outline is required"}), 400
    if not topic:
        return jsonify({"error": "topic is required"}), 400

    try:
        from services.review.review_generator import search_and_assign_papers
        retriever = get_retriever()
        updated_outline, papers = search_and_assign_papers(
            outline=outline,
            topic=topic,
            max_papers=max_papers,
            retriever=retriever,
        )
        return jsonify({"outline": updated_outline, "papers": papers})
    except Exception as e:
        print(f"[ERROR] Search and assign failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Search and assign failed: {str(e)}"}), 500


# ── V25.9: 大纲保存/加载路由 ──

@app.route("/api/review/outline/saved", methods=["GET"])
def list_saved_outlines():
    """V25.9: 列出所有已保存的大纲（按更新时间倒序）。"""
    try:
        store = get_outline_store()
        outlines = store.list()
        return jsonify({"count": len(outlines), "outlines": outlines})
    except Exception as e:
        return jsonify({"error": f"Failed to list outlines: {str(e)}"}), 500


@app.route("/api/review/outline/saved/<name>", methods=["GET"])
def load_saved_outline(name):
    """V25.9: 加载指定名称的已保存大纲。"""
    try:
        store = get_outline_store()
        record = store.load(name)
        if record is None:
            return jsonify({"error": f"Outline '{name}' not found"}), 404
        return jsonify(record)
    except Exception as e:
        return jsonify({"error": f"Failed to load outline: {str(e)}"}), 500


@app.route("/api/review/outline/save", methods=["POST"])
def save_outline():
    """
    V25.9: 保存大纲（JSON body）。

    Body:
      name: 大纲名称（必填）
      topic: 综述主题
      review_type: 综述模板类型
      outline: 段落级大纲 JSON {"sections": [...]}（必填）
      paper_count: 涉及的论文数（可选）
    """
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    outline_data = data.get("outline")
    if not isinstance(outline_data, dict) or "sections" not in outline_data:
        return jsonify({"error": "outline must be a JSON object with 'sections' field"}), 400

    topic = str(data.get("topic", "")).strip()
    review_type = str(data.get("review_type", "narrative")).strip() or "narrative"
    paper_count = int(data.get("paper_count", 0))

    try:
        store = get_outline_store()
        record = store.save(name=name, topic=topic, outline_data=outline_data,
                            review_type=review_type, paper_count=paper_count)
        return jsonify({"status": "saved", "name": record["name"], "updated_at": record["updated_at"]})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to save outline: {str(e)}"}), 500


@app.route("/api/review/outline/saved/<name>", methods=["DELETE"])
def delete_saved_outline(name):
    """V25.9: 删除指定名称的已保存大纲。"""
    try:
        store = get_outline_store()
        deleted = store.delete(name)
        if not deleted:
            return jsonify({"error": f"Outline '{name}' not found"}), 404
        return jsonify({"status": "deleted", "name": name})
    except Exception as e:
        return jsonify({"error": f"Failed to delete outline: {str(e)}"}), 500


@app.route("/api/review/generate", methods=["GET", "POST"])
def generate_review():
    """
    生成综述初稿（V25.0）。

    完整流水线：检索 → 证据抽取 → 大纲生成 → 撰写 → 引用校验 → Markdown 输出。
    核心铁律：每句话必须绑定证据卡片，无证据的句子被校验系统剔除。

    参数:
      topic: 综述主题（必填）
      max_papers: 最多检索的论文数，默认 20
      use_llm_verify: 是否启用 LLM 深度校验，默认 false（确定性校验更快）
      citation_style: 参考文献格式（apa / nature / vancouver），默认 apa
      review_type: 综述模板类型（V25.7）：narrative（叙事型，默认）/ comparative（实验对比型）/ systematic（系统综述型）

    前置条件: Ollama 服务运行，且已拉取模型（默认 qwen2.5:14b）。
    可用环境变量 SCIPAL_LLM_MODEL 覆盖模型名。
    """
    # V25.8: 支持 JSON body 传参（用于 custom_outline 等复杂参数）
    json_body = request.get_json(silent=True) or {}

    # 参数获取优先级：JSON body > query/form
    def get_param(name, default=None):
        if name in json_body:
            return json_body[name]
        return request.values.get(name, default)

    topic = str(get_param("topic", "")).strip()
    if not topic:
        return jsonify({"error": "topic is required"}), 400

    max_papers = int(get_param("max_papers", 20))
    use_llm_verify = str(get_param("use_llm_verify", "false")).lower() in ("true", "1", "yes")
    citation_style = str(get_param("citation_style", "apa")).strip() or "apa"
    # V25.7: 综述模板类型
    review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
    # V25.9: 综述生成语言，默认英文（en），可选中文（zh）
    language = str(get_param("language", "en")).strip().lower() or "en"
    # 校验 review_type 合法性
    valid_review_types = {"narrative", "comparative", "systematic", "story", "experiment", "experimental", "compare", "meta", "meta-analysis"}
    if review_type.lower() not in valid_review_types:
        review_type = "narrative"
    # V25.8: 用户自定义段落级大纲（从 JSON body 读取）
    custom_outline = json_body.get("custom_outline") if isinstance(json_body, dict) else None
    if custom_outline is not None and not isinstance(custom_outline, dict):
        return jsonify({"error": "custom_outline must be a JSON object"}), 400

    try:
        llm = get_llm_client()
        if not llm.is_available():
            if llm.provider == "openai":
                return jsonify({
                    "error": "Cloud API not available",
                    "hint": "Set API key: export SCIPAL_LLM_API_KEY=sk-你的key",
                    "configured_model": llm.model,
                }), 503
            else:
                return jsonify({
                    "error": "Ollama service not available",
                    "hint": "Start Ollama and pull the model: ollama serve && ollama pull qwen2.5:14b",
                    "configured_model": llm.model,
                }), 503

        generator = get_review_generator()
        generator.use_llm_verification = use_llm_verify

        output = generator.generate(
            topic=topic,
            max_papers=max_papers,
            citation_style=citation_style,
            review_type=review_type,
            custom_outline=custom_outline,
            language=language,
        )

        # V25.6: 暂存综述结果（含 sentences 和 evidence_cards，用于前端点击溯源）
        review_id = None
        try:
            store = get_review_store()
            review_id = store.store(
                review_output=output,
                draft=generator._last_draft,
                evidence_cards=generator._last_evidence_cards,
            )
        except Exception as store_err:
            # 暂存失败不影响综述返回
            print(f"[WARN] Review store failed: {store_err}")

        return jsonify({
            "topic": output.topic,
            "markdown": output.markdown,
            "references": output.references,
            "stats": output.stats,
            "warnings": output.warnings,
            "relations": output.relations,
            "conflicts": output.conflicts,
            "review_id": review_id,  # V25.6: 用于前端预览页点击溯源
        })
    except Exception as e:
        return jsonify({"error": f"Review generation failed: {str(e)}"}), 500


@app.route("/api/review/<review_id>", methods=["GET"])
def get_review_detail(review_id):
    """V25.6: 获取综述详情（含 sentences 和 evidence_cards，用于前端预览页点击溯源）。"""
    store = get_review_store()
    entry = store.get(review_id)
    if entry is None:
        return jsonify({"error": "Review not found or expired"}), 404
    return jsonify(entry)


@app.route("/api/review/<review_id>/sentence/<sentence_id>", methods=["GET"])
def get_review_sentence(review_id, sentence_id):
    """V25.6: 获取单个句子的溯源信息（句子详情 + 关联的证据卡片列表）。"""
    store = get_review_store()
    result = store.get_sentence(review_id, sentence_id)
    if result is None:
        return jsonify({"error": "Sentence not found"}), 404
    return jsonify(result)


@app.route("/api/review/llm_status", methods=["GET"])
def review_llm_status():
    """检查综述生成所需的 LLM 服务状态（V25.4: 支持 Ollama 和云端 API）。"""
    try:
        llm = get_llm_client()
        available = llm.is_available()
        models = llm.list_models() if available else []
        provider = llm.provider
        if provider == "openai":
            hint = None if available else "配置 API key: export SCIPAL_LLM_API_KEY=sk-你的key"
        else:
            hint = None if available else "Start Ollama: ollama serve && ollama pull qwen2.5:14b"
        return jsonify({
            "available": available,
            "provider": provider,
            "configured_model": llm.model,
            "installed_models": models,
            "hint": hint,
        })
    except Exception as e:
        return jsonify({"available": False, "error": str(e)}), 500


# V25.11: 列出本地 documents 目录所有 PDF，标记是否已解析
@app.route("/api/papers/local", methods=["GET"])
def list_local_papers():
    """扫描 documents 目录下所有 PDF 文件，交叉查 papers 表标记解析状态。

    Returns:
      papers: [{filename, file_size, modified_at, parsed, paper_id, title, authors, year, paragraph_count}]
    """
    import sqlite3
    import os

    if not DOCUMENTS_DIR.exists():
        return jsonify({"papers": [], "error": "documents directory not found"}), 200

    # 查询所有已解析论文
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT paper_id, filename, title, authors, year, total_paragraphs FROM papers"
    ).fetchall()

    # V25.17: 查询每篇论文的补充材料数量
    supp_counts = {}
    try:
        supp_rows = conn.execute(
            "SELECT paper_id, COUNT(*) as cnt FROM supplementary_files GROUP BY paper_id"
        ).fetchall()
        for r in supp_rows:
            supp_counts[r["paper_id"]] = r["cnt"]
    except Exception:
        pass  # 表可能还不存在（旧数据库），迁移会在启动时创建
    conn.close()

    parsed_map = {}
    for row in rows:
        if row["filename"]:
            parsed_map[row["filename"]] = {
                "paper_id": row["paper_id"],
                "title": row["title"] or row["filename"],
                "authors": row["authors"] or "",
                "year": row["year"],
                "paragraph_count": row["total_paragraphs"] or 0,
                "supp_count": supp_counts.get(row["paper_id"], 0),
            }

    # 扫描 documents 目录
    result = []
    for entry in sorted(DOCUMENTS_DIR.iterdir()):
        if not entry.is_file() or entry.suffix.lower() != ".pdf":
            continue
        filename = entry.name
        stat = entry.stat()
        info = parsed_map.get(filename)
        result.append({
            "filename": filename,
            "file_size": stat.st_size,
            "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified_at": entry.stat().st_mtime,
            "parsed": info is not None,
            "paper_id": info["paper_id"] if info else None,
            "title": info["title"] if info else filename,
            "authors": info["authors"] if info else "",
            "year": info["year"] if info else None,
            "paragraph_count": info["paragraph_count"] if info else 0,
            "supp_count": info["supp_count"] if info else 0,
        })

    # 已解析的排前面，然后按文件名
    result.sort(key=lambda x: (not x["parsed"], x["filename"].lower()))
    return jsonify({"papers": result, "total": len(result), "parsed_count": sum(1 for p in result if p["parsed"])})


# ============================================================
# V33.1: 混合搜索 API（本地 + 在线 NCBI/PMC）
# ============================================================

@app.route("/api/search/hybrid", methods=["GET", "POST"])
def hybrid_search_api():
    """
    V33.1: 混合搜索论文（本地数据库 + 在线 NCBI PubMed/PMC）。

    同时搜索本地和在线，结果合并、三级去重（PMCID/PMID/DOI）、统一排序。
    本地论文标 source="local"，在线新论文标 source="online"。

    参数（GET query 或 POST JSON）：
      q: 搜索关键词（必填）
      top_k: 返回最大结果数（默认 20）
      use_online: 是否使用在线搜索（默认 true）
      online_max: 在线搜索每个数据库最大结果数（默认 30）

    返回：
      {
        "query": str,
        "total": int,
        "local_count": int,
        "online_count": int,
        "online_in_local_count": int,
        "papers": [...],           // 合并后的论文列表
        "local_papers": [...],     // 仅本地论文
        "online_papers": [...],    // 仅在线新论文
      }
    """
    # 兼容 GET 和 POST
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        query = data.get("q", "").strip()
        top_k = int(data.get("top_k", 20))
        use_online = bool(data.get("use_online", True))
        online_max = int(data.get("online_max", 30))
    else:
        query = request.args.get("q", "").strip()
        top_k = int(request.args.get("top_k", 20))
        use_online = request.args.get("use_online", "true").lower() == "true"
        online_max = int(request.args.get("online_max", 30))

    if not query:
        return jsonify({"error": "缺少搜索关键词 q"}), 400

    try:
        retriever = get_hybrid_retriever()
        result = retriever.search_papers(
            query=query,
            top_k=top_k,
            use_online=use_online,
            online_max_results=online_max,
        )
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"混合搜索失败: {str(e)}"}), 500


@app.route("/api/search/online", methods=["GET", "POST"])
def online_search_api():
    """
    V33.1: 仅在线搜索 NCBI PubMed/PMC（不搜本地）。

    参数：
      q: 搜索关键词（必填）
      max_results: 每个数据库最大结果数（默认 30）
      search_pubmed: 是否搜 PubMed（默认 true）
      search_pmc: 是否搜 PMC（默认 true）

    返回：
      {
        "query": str,
        "total": int,
        "pubmed_count": int,
        "pmc_count": int,
        "papers": [...],
      }
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        query = data.get("q", "").strip()
        max_results = int(data.get("max_results", 30))
        search_pubmed = bool(data.get("search_pubmed", True))
        search_pmc = bool(data.get("search_pmc", True))
    else:
        query = request.args.get("q", "").strip()
        max_results = int(request.args.get("max_results", 30))
        search_pubmed = request.args.get("search_pubmed", "true").lower() == "true"
        search_pmc = request.args.get("search_pmc", "true").lower() == "true"

    if not query:
        return jsonify({"error": "缺少搜索关键词 q"}), 400

    try:
        from services.search.online_search import get_online_searcher
        searcher = get_online_searcher()

        results = searcher.search(
            query,
            max_results=max_results,
            search_pubmed=search_pubmed,
            search_pmc=search_pmc,
        )

        # 统计
        pubmed_count = sum(1 for r in results if r.source == "online_pubmed")
        pmc_count = sum(1 for r in results if r.source == "online_pmc")

        return jsonify({
            "query": query,
            "total": len(results),
            "pubmed_count": pubmed_count,
            "pmc_count": pmc_count,
            "papers": [r.to_dict() for r in results],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"在线搜索失败: {str(e)}"}), 500


# ============================================================
# V33.2: 在线文献下载 API（异步下载+增量导入+增量建索引）
# ============================================================

@app.route("/api/search/download_online", methods=["POST"])
def download_online_papers():
    """
    V33.2: 启动在线文献下载任务（异步，后台执行）。

    接收用户勾选的在线文献 PMCID 列表，后台自动：
      1. 下载 PMC XML 全文（自动过滤只有摘要的）
      2. 增量导入到 research.db（不清空旧数据）
      3. 增量建向量索引（只对新论文做 embedding，追加到 chroma）

    Request body (JSON):
      pmc_ids: ["PMC1234567", "PMC7654321", ...] （必填，PMCID 列表）

    Returns:
      {
        "task_id": "dl_abc123...",
        "status": "running",
        "total": 10,
        "message": "下载任务已启动，用 task_id 轮询 /api/search/download_status 获取进度"
      }
    """
    data = request.get_json(silent=True) or {}
    pmc_ids = data.get("pmc_ids", [])

    if not pmc_ids:
        return jsonify({"error": "缺少 pmc_ids 参数（PMCID 列表）"}), 400

    # 规范化 PMCID 格式
    normalized_ids = []
    for pid in pmc_ids:
        pid = str(pid).strip()
        if not pid:
            continue
        if not pid.upper().startswith("PMC"):
            pid = f"PMC{pid}"
        normalized_ids.append(pid.upper())

    if not normalized_ids:
        return jsonify({"error": "pmc_ids 列表为空"}), 400

    try:
        from services.search.online_downloader import get_online_downloader
        downloader = get_online_downloader()
        task_id = downloader.start_download(normalized_ids)

        return jsonify({
            "task_id": task_id,
            "status": "running",
            "total": len(normalized_ids),
            "message": "下载任务已启动，用 task_id 轮询 /api/search/download_status 获取进度",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"启动下载任务失败: {str(e)}"}), 500


@app.route("/api/search/download_status", methods=["GET"])
def download_status():
    """
    V33.2: 查询在线文献下载任务进度。

    Query params:
      task_id: 任务 ID（必填）

    Returns:
      {
        "task_id": "dl_abc123...",
        "status": "running" | "completed" | "failed",
        "current_stage": "downloading" | "importing" | "indexing" | "completed",
        "total": 10,
        "downloaded": 5,
        "download_failed": 0,
        "download_skipped": 2,
        "imported": 5,
        "indexed": 5,
        "new_paper_count": 7,
        "progress_percent": 75,
        "elapsed_seconds": 45.2,
        "error": null
      }
    """
    task_id = request.args.get("task_id", "").strip()

    if not task_id:
        return jsonify({"error": "缺少 task_id 参数"}), 400

    try:
        from services.search.online_downloader import get_task_manager
        manager = get_task_manager()
        task = manager.get_task(task_id)

        if task is None:
            return jsonify({"error": f"任务不存在: {task_id}"}), 404

        return jsonify(task.to_dict())
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"查询任务状态失败: {str(e)}"}), 500


# ============================================================
# V33.3: 下载历史、队列管理、失败重试 API
# ============================================================

@app.route("/api/search/download_history", methods=["GET"])
def download_history():
    """
    V33.3: 获取下载历史记录（按时间倒序）。

    Query params:
      limit: 返回条数（默认 20，最多 50）

    Returns:
      {
        "tasks": [...],  // 任务列表
        "total": int,
        "queue_status": { current_task_id, queue_length, queued_task_ids }
      }
    """
    limit = min(int(request.args.get("limit", 20)), 50)

    try:
        from services.search.online_downloader import get_task_manager
        manager = get_task_manager()
        tasks = manager.list_tasks(limit=limit)
        queue_status = manager.get_queue_status()

        return jsonify({
            "tasks": tasks,
            "total": len(tasks),
            "queue_status": queue_status,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"获取下载历史失败: {str(e)}"}), 500


@app.route("/api/search/download_queue", methods=["GET"])
def download_queue_status():
    """
    V33.3: 获取下载队列状态。

    Returns:
      {
        "current_task_id": str | null,
        "queue_length": int,
        "queued_task_ids": [...],
        "current_task": {...} | null  // 当前任务详情
      }
    """
    try:
        from services.search.online_downloader import get_task_manager
        manager = get_task_manager()
        queue_status = manager.get_queue_status()

        # 获取当前任务详情
        current_task = None
        if queue_status["current_task_id"]:
            task = manager.get_task(queue_status["current_task_id"])
            if task:
                current_task = task.to_dict()

        return jsonify({
            **queue_status,
            "current_task": current_task,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"获取队列状态失败: {str(e)}"}), 500


@app.route("/api/search/retry_download", methods=["POST"])
def retry_download():
    """
    V33.3: 重试下载失败的文献。

    两种模式：
      1. 指定 task_id：重试该任务中下载失败的 PMCID
      2. 指定 pmc_ids：直接重试指定的 PMCID 列表

    Request body (JSON):
      task_id: 任务 ID（可选，与 pmc_ids 二选一）
      pmc_ids: PMCID 列表（可选，与 task_id 二选一）

    Returns:
      {
        "task_id": str,
        "retry_count": int,
        "message": str
      }
    """
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "").strip()
    pmc_ids = data.get("pmc_ids", [])

    # 如果指定了 task_id，从该任务中获取失败的 PMCID
    if task_id:
        try:
            from services.search.online_downloader import get_task_manager
            manager = get_task_manager()
            task = manager.get_task(task_id)
            if task is None:
                return jsonify({"error": f"任务不存在: {task_id}"}), 404
            pmc_ids = task.failed_pmc_ids or []
            if not pmc_ids:
                return jsonify({"error": "该任务没有失败的文献"}), 400
        except Exception as e:
            return jsonify({"error": f"获取任务失败: {str(e)}"}), 500

    if not pmc_ids:
        return jsonify({"error": "缺少 pmc_ids 或 task_id 参数"}), 400

    # 规范化 PMCID
    normalized_ids = []
    for pid in pmc_ids:
        pid = str(pid).strip()
        if not pid:
            continue
        if not pid.upper().startswith("PMC"):
            pid = f"PMC{pid}"
        normalized_ids.append(pid.upper())

    if not normalized_ids:
        return jsonify({"error": "PMCID 列表为空"}), 400

    try:
        from services.search.online_downloader import get_online_downloader
        downloader = get_online_downloader()
        new_task_id = downloader.start_download(normalized_ids)

        return jsonify({
            "task_id": new_task_id,
            "retry_count": len(normalized_ids),
            "message": f"已启动重试任务，共 {len(normalized_ids)} 篇文献",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"启动重试任务失败: {str(e)}"}), 500


@app.route("/api/search/clear_download_history", methods=["POST"])
def clear_download_history():
    """
    V33.3: 清空下载历史记录（只保留正在运行的）。

    Returns:
      { "cleared": int, "message": str }
    """
    try:
        from services.search.online_downloader import get_task_manager
        manager = get_task_manager()
        cleared = manager.clear_history()

        return jsonify({
            "cleared": cleared,
            "message": f"已清空 {cleared} 条历史记录",
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"清空历史失败: {str(e)}"}), 500


@app.route("/api/papers/parse", methods=["POST"])
def parse_local_paper():
    """V25.14: 触发解析一篇本地未解析的 PDF 文献。

    Request body:
      filename: PDF 文件名（在 documents 目录下）

    Returns:
      paper_id, status, title, stats
    """
    import sqlite3
    import os

    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "").strip()

    if not filename:
        return jsonify({"error": "缺少 filename 参数"}), 400

    # 防止路径穿越
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "非法的文件名"}), 400

    pdf_path = DOCUMENTS_DIR / filename
    if not pdf_path.exists():
        return jsonify({"error": f"PDF 文件不存在: {filename}"}), 404

    # 检查是否已解析
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT paper_id, title, total_paragraphs FROM papers WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()

    if row:
        # 已解析，直接返回
        return jsonify({
            "paper_id": row["paper_id"],
            "status": "already_parsed",
            "title": row["title"] or filename,
            "paragraph_count": row["total_paragraphs"] or 0,
        })

    # 未解析，执行解析
    print(f"📄 开始解析: {filename}")

    # 先检查 build_db 目录是否存在
    build_db_dir = PROJECT_ROOT / "build_db"
    if not build_db_dir.exists():
        return jsonify({"error": f"解析失败: build_db 目录不存在 ({build_db_dir})，请确认项目结构完整"}), 500

    try:
        from build_db.parsers.parser_orchestrator import ParserOrchestrator
        from build_db.db_writer import DatabaseWriter
    except ImportError as e:
        # 导入失败时给出更明确的诊断
        import traceback
        print(f"❌ 解析模块导入失败: {e}")
        traceback.print_exc()
        return jsonify({"error": f"解析模块导入失败: {str(e)}。请确认 build_db/ 目录完整且 docling 已安装（pip install docling）"}), 500

    try:
        orchestrator = ParserOrchestrator()
        parsed_result = orchestrator.parse_paper(str(pdf_path))

        db_writer = DatabaseWriter()
        success = db_writer.insert_paper(parsed_result)

        if not success:
            return jsonify({"error": "解析成功但写入数据库失败"}), 500

        paper_id = parsed_result.get("paper_id", "")
        title = parsed_result.get("metadata", {}).get("title", filename)
        paragraph_count = len(parsed_result.get("paragraphs", []))

        print(f"✅ 解析完成: {title} ({paragraph_count} 段落)")
        return jsonify({
            "paper_id": paper_id,
            "status": "parsed",
            "title": title,
            "paragraph_count": paragraph_count,
            "stats": {
                "paragraphs": paragraph_count,
                "figures": len(parsed_result.get("figures", [])),
                "citations": len(parsed_result.get("citations", [])),
            },
        })

    except Exception as e:
        print(f"❌ 解析失败: {filename} - {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"解析失败: {str(e)}"}), 500


@app.route("/api/papers/<paper_id>/pdf", methods=["GET"])
def serve_pdf(paper_id):
    """Serve the original PDF file for a paper (for built-in PDF reader)."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT filename FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    conn.close()
    if not row or not row["filename"]:
        return jsonify({"error": "PDF not found"}), 404

    pdf_path = DOCUMENTS_DIR / row["filename"]
    if not pdf_path.exists():
        return jsonify({"error": f"PDF file missing: {row['filename']}"}), 404

    return send_from_directory(
        str(DOCUMENTS_DIR), row["filename"],
        mimetype="application/pdf")


# ============================================================
# V26.4: Abstract API - 根据 PMID 查询摘要
# ============================================================

@app.route("/api/abstracts/list", methods=["GET"])
def list_abstracts():
    """V26.5: 查询摘要库论文列表"""
    import sqlite3

    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    search = request.args.get('search', '', type=str)

    abstract_db_path = PROJECT_ROOT / "data" / "abstracts.db"

    if not abstract_db_path.exists():
        return jsonify({"error": "摘要数据库不存在"}), 404

    conn = sqlite3.connect(str(abstract_db_path))
    conn.row_factory = sqlite3.Row

    # 查询总数
    if search:
        count_sql = "SELECT COUNT(*) as total FROM papers WHERE title LIKE ? OR abstract LIKE ?"
        count_row = conn.execute(count_sql, (f'%{search}%', f'%{search}%')).fetchone()
    else:
        count_row = conn.execute("SELECT COUNT(*) as total FROM papers").fetchone()
    total = count_row["total"]

    # 查询分页数据
    offset = (page - 1) * page_size
    if search:
        list_sql = "SELECT pmid, doi, title, authors, journal, year, topic FROM papers WHERE title LIKE ? OR abstract LIKE ? ORDER BY year DESC LIMIT ? OFFSET ?"
        rows = conn.execute(list_sql, (f'%{search}%', f'%{search}%', page_size, offset)).fetchall()
    else:
        list_sql = "SELECT pmid, doi, title, authors, journal, year, topic FROM papers ORDER BY year DESC LIMIT ? OFFSET ?"
        rows = conn.execute(list_sql, (page_size, offset)).fetchall()

    conn.close()

    papers = []
    for row in rows:
        papers.append({
            "paper_id": str(row["pmid"]),
            "title": row["title"],
            "authors": row["authors"],
            "journal": row["journal"],
            "year": row["year"],
            "topic": row["topic"],
            "source": "abstract",
        })

    return jsonify({
        "papers": papers,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    })


@app.route("/api/abstracts/<paper_id>", methods=["GET"])
def get_abstract(paper_id):
    """根据 PMID 查询摘要内容"""
    import sqlite3
    from pathlib import Path

    # abstracts.db 的路径
    abstract_db_path = PROJECT_ROOT / "data" / "abstracts.db"

    if not abstract_db_path.exists():
        return jsonify({"error": "摘要数据库不存在"}), 404

    conn = sqlite3.connect(str(abstract_db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT pmid, doi, title, abstract, authors, journal, year, topic FROM papers WHERE pmid = ?",
        (paper_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "摘要未找到"}), 404

    return jsonify({
        "pmid": row["pmid"],
        "doi": row["doi"],
        "title": row["title"],
        "abstract": row["abstract"],
        "authors": row["authors"],
        "journal": row["journal"],
        "year": row["year"],
        "topic": row["topic"],
    })


# ============================================================
# V25.17: Supplementary files API
# ============================================================

@app.route("/api/papers/<paper_id>/supplementary", methods=["GET"])
def list_supplementary_files(paper_id):
    """List all supplementary files for a paper."""
    from build_db.db_writer import DatabaseWriter
    writer = DatabaseWriter()
    files = writer.get_supplementary_files(paper_id)
    return jsonify({"supplementary_files": files})


@app.route("/api/papers/<paper_id>/supplementary", methods=["POST"])
def upload_supplementary_file(paper_id):
    """Upload a supplementary file and associate it with a paper.
    
    Request: multipart/form-data with 'file' field and optional 'description'
    """
    import uuid
    from build_db.db_writer import DatabaseWriter

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files['file']
    if not uploaded.filename:
        return jsonify({"error": "Empty filename"}), 400

    # Verify paper exists
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": f"Paper {paper_id} not found"}), 404

    # Save file to documents directory
    original_filename = uploaded.filename
    # Handle duplicate filenames
    save_name = original_filename
    base, ext = os.path.splitext(original_filename)
    counter = 1
    while (DOCUMENTS_DIR / save_name).exists():
        save_name = f"{base}_{counter}{ext}"
        counter += 1

    save_path = DOCUMENTS_DIR / save_name
    uploaded.save(str(save_path))
    file_size = save_path.stat().st_size

    # Determine file type
    file_type = ext.lower().lstrip('.') or 'unknown'

    # Generate supp_id
    supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

    # Get description from form
    description = request.form.get('description', '')

    # Save to database
    writer = DatabaseWriter()
    success = writer.insert_supplementary_file({
        "supp_id": supp_id,
        "paper_id": paper_id,
        "filename": save_name,
        "file_type": file_type,
        "file_path": str(save_path),
        "file_size": file_size,
        "description": description,
    })

    if not success:
        # Clean up file if DB insert failed
        save_path.unlink(missing_ok=True)
        return jsonify({"error": "Failed to save supplementary file record"}), 500

    print(f"📎 Supplementary file added: {save_name} -> {paper_id}")
    return jsonify({
        "success": True,
        "supp_id": supp_id,
        "filename": save_name,
        "file_type": file_type,
        "file_size": file_size,
    })


@app.route("/api/papers/<paper_id>/supplementary/<supp_id>/download", methods=["GET"])
def download_supplementary_file(paper_id, supp_id):
    """Download/serve a supplementary file."""
    from build_db.db_writer import DatabaseWriter
    writer = DatabaseWriter()
    files = writer.get_supplementary_files(paper_id)
    target = next((f for f in files if f["supp_id"] == supp_id), None)
    if not target:
        return jsonify({"error": "Supplementary file not found"}), 404

    file_path = Path(target["file_path"])
    if not file_path.exists():
        return jsonify({"error": f"File missing: {target['filename']}"}), 404

    return send_from_directory(
        str(file_path.parent), file_path.name,
        as_attachment=False)


@app.route("/api/papers/<paper_id>/supplementary/<supp_id>", methods=["DELETE"])
def delete_supplementary_file(paper_id, supp_id):
    """Delete a supplementary file record and optionally the file itself.
    
    Query param: delete_file=1 to also delete the actual file
    """
    from build_db.db_writer import DatabaseWriter
    writer = DatabaseWriter()
    files = writer.get_supplementary_files(paper_id)
    target = next((f for f in files if f["supp_id"] == supp_id), None)
    if not target:
        return jsonify({"error": "Supplementary file not found"}), 404

    # Delete DB record
    success = writer.delete_supplementary_file(supp_id)
    if not success:
        return jsonify({"error": "Failed to delete record"}), 500

    # Optionally delete actual file
    delete_file = request.args.get('delete_file', '0') == '1'
    if delete_file:
        file_path = Path(target["file_path"])
        if file_path.exists():
            file_path.unlink()
            print(f"🗑️  Supplementary file deleted: {target['filename']}")

    return jsonify({"success": True, "supp_id": supp_id})


# ============================================================
# V25.17: 导入文献（正文 + 可选补充材料，一次上传）
# ============================================================

@app.route("/api/papers/import", methods=["POST"])
def import_paper():
    """导入一篇文献：正文PDF（必选）+ 补充材料（可选，多选）。

    只负责保存文件到 documents 目录，不触发解析。
    前端拿到 filename 后再调用 /api/papers/parse 触发解析，
    解析完成后用 paper_id 把补充材料逐个关联。

    Request: multipart/form-data
      - paper: 正文 PDF 文件（必选）
      - supplementary: 补充材料文件（可选，可多个同名字段）
    """
    import uuid

    # 正文 PDF（必选）
    if 'paper' not in request.files:
        return jsonify({"error": "缺少正文 PDF 文件（paper 字段）"}), 400

    paper_file = request.files['paper']
    if not paper_file.filename:
        return jsonify({"error": "正文文件名为空"}), 400

    # 保存正文 PDF（处理重名）
    paper_filename = paper_file.filename
    base, ext = os.path.splitext(paper_filename)
    counter = 1
    while (DOCUMENTS_DIR / paper_filename).exists():
        paper_filename = f"{base}_{counter}{ext}"
        counter += 1
    paper_file.save(str(DOCUMENTS_DIR / paper_filename))
    paper_size = (DOCUMENTS_DIR / paper_filename).stat().st_size
    print(f"📥 导入正文: {paper_filename} ({paper_size / 1024:.0f} KB)")

    # 补充材料（可选，多选）
    supp_files = request.files.getlist('supplementary')
    saved_supp = []
    for supp_file in supp_files:
        if not supp_file.filename:
            continue
        # 保存补充材料（处理重名）
        supp_filename = supp_file.filename
        s_base, s_ext = os.path.splitext(supp_filename)
        s_counter = 1
        while (DOCUMENTS_DIR / supp_filename).exists():
            supp_filename = f"{s_base}_{s_counter}{s_ext}"
            s_counter += 1
        supp_file.save(str(DOCUMENTS_DIR / supp_filename))
        supp_size = (DOCUMENTS_DIR / supp_filename).stat().st_size
        file_type = s_ext.lower().lstrip('.') or 'unknown'
        saved_supp.append({
            "filename": supp_filename,
            "original_name": supp_file.filename,
            "file_type": file_type,
            "file_size": supp_size,
        })
        print(f"📎 导入补充材料: {supp_filename} ({supp_size / 1024:.0f} KB)")

    return jsonify({
        "success": True,
        "paper_filename": paper_filename,
        "paper_size": paper_size,
        "supplementary_files": saved_supp,
        "supplementary_count": len(saved_supp),
    })


@app.route("/api/papers/<paper_id>/supplementary/link", methods=["POST"])
def link_supplementary_file(paper_id):
    """将 documents 目录中已存在的文件关联为某篇论文的补充材料。
    用于导入流程：文件已通过 /api/papers/import 上传，解析得到 paper_id 后，
    按文件名直接关联，不需要重新上传文件内容。

    Request body: {"filename": "xxx.pdf", "description": "..."}
    """
    import uuid
    from build_db.db_writer import DatabaseWriter

    data = request.get_json(force=True)
    filename = data.get('filename', '')
    description = data.get('description', '')

    if not filename:
        return jsonify({"error": "缺少 filename"}), 400

    # 验证论文存在
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": f"Paper {paper_id} not found"}), 404

    # 验证文件存在
    file_path = DOCUMENTS_DIR / filename
    if not file_path.exists():
        return jsonify({"error": f"文件不存在: {filename}"}), 404

    file_size = file_path.stat().st_size
    file_type = file_path.suffix.lower().lstrip('.') or 'unknown'
    supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

    writer = DatabaseWriter()
    success = writer.insert_supplementary_file({
        "supp_id": supp_id,
        "paper_id": paper_id,
        "filename": filename,
        "file_type": file_type,
        "file_path": str(file_path),
        "file_size": file_size,
        "description": description,
    })

    if not success:
        return jsonify({"error": "数据库写入失败"}), 500

    print(f"🔗 补充材料关联: {filename} -> {paper_id}")
    return jsonify({
        "success": True,
        "supp_id": supp_id,
        "filename": filename,
        "file_type": file_type,
        "file_size": file_size,
    })


# V25.10: PDF 标注（添加/删除注释，写入 PDF 文件持久化）
@app.route("/api/papers/<paper_id>/annotate", methods=["POST"])
def annotate_pdf(paper_id):
    """添加或删除 PDF 注释。注释直接写入 PDF 文件。

    Request body:
      action: "add" | "delete"
      page: 页码（从1开始）
      type: "highlight" | "underline" | "text"
      rect: [x0, y0, x1, y1] PDF标准坐标（左下原点）
      color: [r, g, b] 可选，0-1
      text: 注释文本 可选
    """
    from services.pdf.annotator import PdfAnnotator

    data = request.get_json(silent=True) or {}
    action = data.get("action", "add")
    page = data.get("page")
    annot_type = data.get("type")
    rect = data.get("rect")
    color = data.get("color")
    text = data.get("text", "")

    if not page or not annot_type or not rect:
        return jsonify({"error": "缺少必要参数: page, type, rect"}), 400

    annotator = PdfAnnotator(str(DB_PATH), str(DOCUMENTS_DIR))

    if action == "delete":
        result = annotator.delete_annotation(paper_id, page, annot_type, rect, text)
    else:
        result = annotator.add_annotation(paper_id, page, annot_type, rect, color, text)

    if not result.get("success"):
        return jsonify({"error": result.get("error", "标注操作失败")}), 500

    return jsonify(result)


# V25.10: 列出 PDF 中的标注
@app.route("/api/papers/<paper_id>/annotations", methods=["GET"])
def list_pdf_annotations(paper_id):
    """列出 PDF 中的所有标注（用于前端渲染可点击的删除覆盖层）。

    Query params:
      page: 页码（可选，不填则列出所有页）
    """
    from services.pdf.annotator import PdfAnnotator

    page = request.args.get("page", type=int)
    annotator = PdfAnnotator(str(DB_PATH), str(DOCUMENTS_DIR))
    result = annotator.list_annotations(paper_id, page)

    if not result.get("success"):
        return jsonify({"error": result.get("error", "获取标注列表失败")}), 500

    return jsonify(result)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(FRONTEND_DIR), path)


# ---------------------------------------------------------------------------
# Database migration (V25.15: 自动为已有数据库添加缺失字段)
# ---------------------------------------------------------------------------

def run_db_migrations():
    """启动时自动检查并添加缺失的数据库字段，幂等安全。"""
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        # 获取 papers 表现有列
        cursor.execute("PRAGMA table_info(papers)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        # 需要添加的字段
        missing = []
        for col in ["volume", "issue", "pages"]:
            if col not in existing_cols:
                missing.append(col)
        if missing:
            for col in missing:
                cursor.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT")
            conn.commit()
            print(f"🔧 数据库迁移完成: papers 表新增字段 {missing}")

        # V25.17: 检查 supplementary_files 表是否存在，不存在则创建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='supplementary_files'")
        if not cursor.fetchone():
            cursor.execute('''
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
            )
            ''')
            conn.commit()
            print("🔧 数据库迁移完成: 新增 supplementary_files 表")

        # V33.12: 检查 tasks 表是否存在，不存在则创建
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                progress_text TEXT DEFAULT '',
                progress_pct REAL DEFAULT 0,
                params TEXT,
                result TEXT,
                error TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
            ''')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at)")
            conn.commit()
            print("🔧 数据库迁移完成: 新增 tasks 表（统一任务表）")

        conn.close()
    except Exception as e:
        print(f"⚠️  数据库迁移跳过（不影响运行）: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("SCIPAL_HOST", "0.0.0.0")
    port = int(os.environ.get("SCIPAL_PORT", "5000"))
    debug = os.environ.get("SCIPAL_DEBUG", "0") == "1"
    print(f"🧪 Sci-Pal API V25.17 — http://{host}:{port}")
    print(f"   DB: {DB_PATH}")
    print(f"   Frontend: {FRONTEND_DIR}")
    run_db_migrations()

    # V33.13: 启动时预热模型，避免第一次请求超时
    print("🔥 启动预热：加载模型...")
    try:
        get_retriever()
        print("  ✅ 检索模型已加载")
    except Exception as e:
        print(f"  ⚠️ 检索模型预热失败: {e}")
    try:
        get_llm_client()
        print("  ✅ LLM 客户端已加载")
    except Exception as e:
        print(f"  ⚠️ LLM 预热失败: {e}")
    print("🔥 预热完成，启动服务")

    app.run(host=host, port=port, debug=debug, threaded=False)
