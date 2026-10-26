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

# B2b 试点：统一响应契约（仅这两个只读路由使用，其余路由暂不动）
from contracts import InternalError, fail, ok
from routes.ingest import build_ingest_blueprint
from routes.papers import build_papers_blueprint
from routes.reviews import build_reviews_blueprint
from routes.search import build_search_blueprint
from routes.system import build_system_blueprint

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
        # V33.17 C-3: 复用全局检索器单例，不再让 QAService 自建一套
        _qa_service = QAService(retriever=get_retriever())
    return _qa_service


def get_llm_client():
    """Lazy-load LLM client (V25.4: 支持 Ollama 和云端 OpenAI 兼容 API)。"""
    global _llm_client
    if _llm_client is None:
        from services.review.llm_client import create_llm_client
        _llm_client = create_llm_client()
    return _llm_client


# V33.17 C-2: 同步 /api/review/generate 用的是**共享单例**（会写 use_llm_verification，
# 并读取 _last_draft / _last_evidence_cards 这两个中间结果）。threaded=True 之后，
# 并发调用会互相覆盖参数与结果 → 用模块级锁把这条同步路径串行化。
# 注意：异步版 /api/review/generate_async **不用**这把锁 —— 它每个任务 new 私有实例，天然隔离。
_review_generate_lock = threading.Lock()


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


# B3a: system 域只读路由（graph/stats、communities）已移入 routes/system.py
app.register_blueprint(
    build_system_blueprint(db_path=DB_PATH, get_graph=get_graph, log=app.logger)
)
# B3b: papers 域只读路由（列表/详情/引文邻居）已移入 routes/papers.py
app.register_blueprint(
    build_papers_blueprint(db_path=DB_PATH, get_graph=get_graph, log=app.logger)
)


def _download_task_manager():
    """Lazy accessor so routes/search.py never imports the download subsystem."""
    from services.search.online_downloader import get_task_manager

    return get_task_manager()


# B3c: 下载状态/历史/队列三条只读路由已移入 routes/search.py
app.register_blueprint(
    build_search_blueprint(get_task_manager=_download_task_manager, log=app.logger)
)

# B4a: 综述查询（reviews 表，CLI/外部生成的综述对前端可见）
app.register_blueprint(
    build_reviews_blueprint(db_path=DB_PATH, log=app.logger)
)

_ingest_service = None


def get_ingest_service():
    """Lazy: importing ingest pulls chromadb/torch only when first used."""
    global _ingest_service
    if _ingest_service is None:
        from services.search.ingest import IngestService

        _ingest_service = IngestService(
            db_path=DB_PATH,
            xml_dir=PROJECT_ROOT / "documents_xml",
            chroma_path=PROJECT_ROOT / "data" / "chroma",
            log=app.logger.info,
        )
    return _ingest_service


# B4b: 异步“下载 + 入库 + 向量化”（只提交、立即返回 task_id）
app.register_blueprint(
    build_ingest_blueprint(get_service=get_ingest_service, log=app.logger)
)


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
        "version": "V33.17",
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


@app.route("/api/qa/ask_async", methods=["POST"])
def qa_ask_async():
    """V33.17 C-3: 异步 RAG 问答（立即返回 task_id）。

    参数与同步版 `/api/qa/ask` **完全一致**：
      question(必填) / paper_id(可选) / diagnostics=false

    返回：{"task_id": "..."}
    轮询：GET /api/review/task/<task_id>（status=running/completed/failed/cancelled）
    取消：POST /api/review/cancel/<task_id>

    ⚠️ 取消限制（如实说明）：
      `QAService.ask()` 内部是**黑盒调用**（检索 → 组 envelope → LLM 生成 → 防幻觉校验），
      没有可插入的中间阶段 → 只在**提交前**与 `ask()` 返回后各检查一次 `is_cancelled`。
      **一旦进入 ask() 就无法中断**，取消请求要等整个 ask() 返回后才被观察到。

    隔离：QAService 是共享单例（C-3 起注入 `get_retriever()`，不再自建检索栈）。
      ask() 本身无 `use_*` 这类可写状态，并发调用不会互相污染；代价是并发时争 CPU。
    """
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    paper_id = data.get("paper_id") or None
    include_diagnostics = bool(data.get("diagnostics", False))

    if not question:
        return jsonify({"error": "参数 'question' 不能为空"}), 400

    task_id = task_manager.create_task("qa_ask")

    def run_task():
        try:
            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            qa = get_qa_service()
            task_manager.update_progress(task_id, "检索证据并生成回答（不可中断）...")
            result = qa.ask(
                question=question,
                paper_id=paper_id,
                include_diagnostics=include_diagnostics,
            )

            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            task_manager.update_progress(task_id, "整理结果...")
            task_manager.complete_task(task_id, result)
        except Exception as e:
            print(f"[ERROR] Async Q&A failed: {e}")
            task_manager.fail_task(task_id, str(e))

    threading.Thread(target=run_task, daemon=True).start()
    return jsonify({"task_id": task_id})


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
        # V33.17 C-3: 注入共享检索器。此前每次请求都 new AgenticSearcher，
        # 其默认构造会再建一套 UnifiedRetriever（饿汉加载模型）→ 单次要 40~100 s。
        agentic = AgenticSearcher(
            retriever=get_retriever(),
            max_hops=max_hops, min_coverage=min_coverage)
        result = agentic.search(
            q, paper_id=paper_id, top_paragraphs=top_paragraphs)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Agentic search failed: {str(e)}"}), 500


@app.route("/api/agentic/search_async", methods=["POST"])
def agentic_search_async():
    """V33.17 C-3: 异步多跳检索（立即返回 task_id）。

    参数与同步版 `/api/agentic/search` 一致：
      q(必填) / max_hops=3（钳 1–5）/ min_coverage=0.6 / top_paragraphs=6 / paper_id(可选)

    返回：{"task_id": "..."}
    轮询：GET /api/review/task/<task_id>
    取消：POST /api/review/cancel/<task_id>

    ⚠️ 取消限制（如实说明）：
      `AgenticSearcher.search()` 是**整条多跳循环**（每跳检索 → 抽取 → 判断覆盖率），
      其内部没有暴露取消钩子 → 只在**提交前**与 `search()` 返回后各检查一次。
      取消要等当前整轮多跳跑完才生效，**跳内不可中断**。
      多跳本身是分钟级（最小参数 max_hops=1 也需要数十秒）。
    """
    data = request.get_json(silent=True) or {}
    q = str(data.get("q", "")).strip()
    max_hops = max(1, min(int(data.get("max_hops", 3)), 5))
    min_coverage = float(data.get("min_coverage", 0.6))
    top_paragraphs = int(data.get("top_paragraphs", 6))
    paper_id = data.get("paper_id") or None

    if not q:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    task_id = task_manager.create_task("agentic_search")

    def run_task():
        try:
            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            from services.search.agentic_search import AgenticSearcher

            # E-1 后的写法：注入共享检索器，不再每次请求重建检索栈
            agentic = AgenticSearcher(
                retriever=get_retriever(),
                max_hops=max_hops,
                min_coverage=min_coverage,
            )
            task_manager.update_progress(task_id, "执行多跳检索（不可中断）...")
            result = agentic.search(q, paper_id=paper_id, top_paragraphs=top_paragraphs)

            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            task_manager.update_progress(task_id, "整理结果...")
            task_manager.complete_task(task_id, result)
        except Exception as e:
            print(f"[ERROR] Async agentic search failed: {e}")
            task_manager.fail_task(task_id, str(e))

    threading.Thread(target=run_task, daemon=True).start()
    return jsonify({"task_id": task_id})


# papers 域只读路由（列表/详情/引文邻居）已迁入 routes/papers.py（B3b）


# paper_detail 已迁入 routes/papers.py（B3b）


# paper_graph 已迁入 routes/papers.py（B3b）


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

        # V33.17 C-2: 共享单例 + threaded=True → 必须串行，否则 use_llm_verification
        # 与 _last_draft/_last_evidence_cards 会被并发任务互相覆盖。
        with _review_generate_lock:
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


@app.route("/api/review/generate_async", methods=["POST"])
def generate_review_async():
    """V33.17 C-2: 异步生成综述初稿（立即返回 task_id）。

    参数与同步版 `/api/review/generate` **完全一致**：
      topic(必填) / max_papers=20 / use_llm_verify=false / citation_style="apa" /
      review_type="narrative" / language="en" / custom_outline(JSON object, 可选)

    返回：{"task_id": "..."}（立即，不等结果）

    轮询：GET /api/review/task/<task_id>（status=running/completed/failed/cancelled）
    取消：POST /api/review/cancel/<task_id>

    ⚠️ 取消语义（如实说明）：
      只在**阶段之间**生效 —— 检索前 / 证据抽取前 / 大纲前 / 撰写前 / 校验前，共 5 个点。
      各阶段内部是原子的：**正在撰写正文时不可中断**，取消要等这一段 LLM 撰写跑完，
      才会在「校验前」被观察到。所以取消粒度是「阶段级」，不是「句子级」。

    并发隔离：每个任务 new 一个私有 ReviewGenerator（注入的 llm_client / retriever
      仍是全局单例，模型不重复加载），因此两个任务的 use_llm_verification 不会串台。
    """
    json_body = request.get_json(silent=True) or {}

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
    review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
    language = str(get_param("language", "en")).strip().lower() or "en"
    valid_review_types = {
        "narrative", "comparative", "systematic",
        "story", "experiment", "experimental", "compare", "meta", "meta-analysis",
    }
    if review_type.lower() not in valid_review_types:
        review_type = "narrative"
    custom_outline = json_body.get("custom_outline") if isinstance(json_body, dict) else None
    if custom_outline is not None and not isinstance(custom_outline, dict):
        return jsonify({"error": "custom_outline must be a JSON object"}), 400

    task_id = task_manager.create_task("generate_review")

    def run_task():
        try:
            llm = get_llm_client()
            if not llm.is_available():
                task_manager.fail_task(task_id, "LLM not available")
                return

            # V33.17 C-2: **每个任务 new 私有实例**，绝不复用 get_review_generator() 单例 —— 
            # 单例的 use_llm_verification 与 _last_draft/_last_evidence_cards 会被并发任务覆盖。
            # 注入的 llm_client / retriever 本身是全局单例，模型不会重复加载。
            from services.review.review_generator import ReviewGenerator

            generator = ReviewGenerator(
                llm_client=get_llm_client(),
                retriever=get_retriever(),
                use_llm_verification=use_llm_verify,
                db_path=str(DB_PATH),
            )

            output = generator.generate(
                topic=topic,
                max_papers=max_papers,
                citation_style=citation_style,
                review_type=review_type,
                custom_outline=custom_outline,
                language=language,
                task_id=task_id,  # C-2: 阶段间取消检查 + 进度上报
            )

            review_id = None
            try:
                store = get_review_store()
                review_id = store.store(
                    review_output=output,
                    draft=generator._last_draft,
                    evidence_cards=generator._last_evidence_cards,
                )
            except Exception as store_err:
                print(f"[WARN] Review store failed: {store_err}")

            task_manager.complete_task(task_id, {
                "topic": output.topic,
                "markdown": output.markdown,
                "references": output.references,
                "stats": output.stats,
                "warnings": output.warnings,
                "relations": output.relations,
                "conflicts": output.conflicts,
                "review_id": review_id,
                # C-2: 回显本次任务实际使用的参数，便于验证并发任务没有串台
                "use_llm_verify": use_llm_verify,
                "max_papers": max_papers,
                "review_type": review_type,
                "language": language,
            })
        except Exception as e:
            if "Task cancelled by user" in str(e):
                print("[INFO] Async review generation cancelled by user")
                task_manager.cancel_task(task_id)
            else:
                print(f"[ERROR] Async review generation failed: {e}")
                import traceback
                traceback.print_exc()
                task_manager.fail_task(task_id, str(e))

    thread = threading.Thread(target=run_task, daemon=True)
    thread.start()

    return jsonify({"task_id": task_id})


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
        return jsonify(ok({
            "available": available,
            "provider": provider,
            "configured_model": llm.model,
            "installed_models": models,
            "hint": hint,
        }))
    except Exception:
        app.logger.exception("review_llm_status failed")
        error = InternalError("LLM status check failed")
        return jsonify(fail(error)), error.status


# ---------------------------------------------------------------------------
# V33.17-6B补丁: 「哪条记录才算数」的唯一口径
#
# papers.filename **没有**唯一约束（索引只有 idx_papers_doi / idx_papers_title），
# 同一份 PDF 可能同时存在 `paper_X_<hash>`（正常，如 224 段）与
# `paper_X_<hash>_mineru`（空壳，0 段）两行。裸 `fetchone()` 取到哪条取决于物理
# 行序 → 同步路由 / 异步快路径 / `/api/papers/local` 会给出互相矛盾的答案
# （实测同一文件：快路径 224、papers/local 0）。
#
# 口径：**段落数多者优先；并列时取创建更早的**（原始入库那条）。
# ⚠️ 只统一「读取口径」，**不删** `_mineru` 空壳行 —— 那是数据清理，另议。
# ---------------------------------------------------------------------------
_PARSED_PAPER_ORDER = "ORDER BY total_paragraphs DESC, created_at ASC LIMIT 1"


def _find_parsed_paper(filename: str, conn=None):
    """按 filename 取「最有效」的一条已解析记录（`sqlite3.Row`）；没有返回 None。

    这是**唯一口径**，三处调用点都走它：
      · 同步 `POST /api/papers/parse`
      · 异步 `POST /api/papers/parse_async` 的快路径
      · `GET /api/papers/local` 的 parsed_map

    Args:
        filename: `papers.filename`（磁盘上的 PDF 文件名）
        conn: 可选，复用调用方已打开的连接（`/api/papers/local` 要扫 77 个文件，
              避免 77 次开关连接）。为 None 时自己开关。
    """
    import sqlite3

    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT paper_id, filename, title, authors, year, total_paragraphs "
            f"FROM papers WHERE filename = ? {_PARSED_PAPER_ORDER}",
            (filename,),
        ).fetchone()
    finally:
        if own_conn:
            conn.close()


# V25.11: 列出本地 documents 目录所有 PDF，标记是否已解析
@app.route("/api/papers/local", methods=["GET"])
def list_local_papers():
    """扫描 documents 目录下所有 PDF 文件，交叉查 papers 表标记解析状态。

    Returns:
      papers: [{filename, file_size, modified_at, parsed, paper_id, title, authors, year, paragraph_count}]
    """
    import sqlite3

    if not DOCUMENTS_DIR.exists():
        # ⚠️ 状态码**保持 200**：前端也在用这个路由，返回 4xx 可能让页面报错。
        # 「目录不存在」由 MCP 侧（search_server.list_local_papers）据 error 字段
        # 如实上报成 {"ok": false, ...}，不再伪装成「0 篇」。
        return jsonify({"papers": [], "error": "documents directory not found"}), 200

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

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

    # 扫描 documents 目录。每个文件名都走 _find_parsed_paper（统一口径），
    # 不再用「后写覆盖」的 parsed_map —— 否则 _mineru 空壳行会把 224 段覆盖成 0。
    result = []
    try:
        for entry in sorted(DOCUMENTS_DIR.iterdir()):
            if not entry.is_file() or entry.suffix.lower() != ".pdf":
                continue
            filename = entry.name
            stat = entry.stat()
            info = _find_parsed_paper(filename, conn=conn)
            result.append({
                "filename": filename,
                "file_size": stat.st_size,
                "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified_at": stat.st_mtime,
                "parsed": info is not None,
                "paper_id": info["paper_id"] if info else None,
                "title": (info["title"] or filename) if info else filename,
                "authors": (info["authors"] or "") if info else "",
                "year": info["year"] if info else None,
                "paragraph_count": (info["total_paragraphs"] or 0) if info else 0,
                "supp_count": supp_counts.get(info["paper_id"], 0) if info else 0,
            })
    finally:
        conn.close()

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


# download_status 已迁入 routes/search.py（B3c）


# ============================================================
# V33.3: 下载历史、队列管理、失败重试 API
# ============================================================

# download_history 已迁入 routes/search.py（B3c）


# download_queue 已迁入 routes/search.py（B3c）


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


# ---------------------------------------------------------------------------
# V33.17-6B补丁: 解析 + 写库的**唯一实现**与**唯一那把锁**
#
# 为什么抽出来：`_parse_lock` 原先只有异步路由使用，同步路由（前端「解析」按钮）
# 直接跑 docling → 前端点一次 + MCP 提交一次 = 两份 docling 并发，
# 正是这把锁的注释里明确要防的「双份内存 + 抢 CPU」。锁必须下沉到唯一实现里。
#
# ⚠️ 两个解析入口都只调用 `_parse_and_store()`，**不许**在外面再
#    `_parse_lock.acquire()` —— `threading.Lock` 不可重入，会自锁。
#    异步路由为了显示「排队中」只做一次「非阻塞试抢 + 立刻归还」。
# ---------------------------------------------------------------------------
_parse_lock = threading.Lock()

# T3-3: 解析任务并发上限。超过就直接 429，**不许静默排队**。
# 为什么是 3：单实例部署；docling 一次只跑一个（`_parse_lock` 串行），
# 另外给「前端一键」与「MCP 提交」各留一个排队位。再多只是把线程堆在锁上。
PARSE_MAX_CONCURRENT = 3

# 准入锁：与 `_parse_lock` **分开**，只保护「查 running 数 + create_task」这一小段，
# 避免准入判定的开销被解析串行化牵连（否则第 4 个请求要等解析完才拿到 429）。
_parse_admit_lock = threading.Lock()


def _parse_running_count() -> int:
    """当前处于 running 的解析任务数（口径：type='parse_paper' AND status='running'）。

    不含 completed / failed / cancelled —— 那些已经释放了并发额度。
    """
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE type = 'parse_paper' AND status = 'running'"
        ).fetchone()[0]
    finally:
        conn.close()


class ParseStoreError(RuntimeError):
    """解析成功、但写库失败（与「解析本身失败」区分，便于路由给出准确的 error）。"""


class ParseCancelled(RuntimeError):
    """任务已取消，本次解析放弃（**数据不进库**）。

    T3-1: `stage` 标明取消生效的阶段，供日志区分：
      · `排队期间` —— 拿到锁后发现已被取消，**连 docling 都不跑**；
      · `解析后`   —— docling 已跑完，写库前发现已被取消。
    """

    def __init__(self, message: str, stage: str = "") -> None:
        super().__init__(message)
        self.stage = stage


def _parse_and_store(
    pdf_path, filename: str, before_store=None, on_acquired=None, on_waiting=None
) -> Dict:
    """docling 解析 + 写库，全程持有 `_parse_lock`（串行化）。

    Args:
        pdf_path: PDF 绝对路径
        filename: 原始文件名（metadata 缺 title 时兜底）
        before_store: 可选回调，在**解析完成后、写库之前**、**锁内**调用。
            返回 True 表示放弃写库（异步路由用它做取消的最后一道闸）；
            回调里可以顺带更新进度（此刻任务仍是 running，写得进去）。
        on_waiting: 可选回调，在**确认要排队**（试抢锁失败）时、阻塞取锁之前调用。
            必须放在**模块 import 之后**：docling 的 import 首次要 10~15 秒，
            放在 import 之前试抢会摸到一个「暂时空闲」的锁，从而漏报排队（T4-2）。
        on_acquired: 可选回调，在 **`_parse_lock` 已取得、但尚未开始解析** 时调用
            （`with` 块内第一行，早于 `ParserOrchestrator()` 构造）。
            用途：把「排队中」切成「解析中」—— 排队期间进度文案必须停在
            「排队中」，否则排队完全不可观测（T4-2）。
            异常传播：回调抛异常 = 放弃本次解析，锁由 `with` 自动释放，
            异常原样抛给调用方（不吞、不转成 ParseStoreError）。

    Returns:
        `{"paper_id", "title", "paragraph_count", "stats"}`

    Raises:
        ParseCancelled: `before_store` 返回 True（**未写库**）
        ParseStoreError: `insert_paper` 返回 False
        ImportError: build_db 解析模块不可用（在取锁之前就抛，不会卡住队列）
        Exception: docling 解析本身失败；或 `on_acquired` / `before_store` 抛出的异常
    """
    from build_db.parsers.parser_orchestrator import ParserOrchestrator
    from build_db.db_writer import DatabaseWriter

    # T4-2: 试抢一次判「要不要排队」，**必须在 import 之后**。
    # docling 的 import 首次要 10~15 秒：若在 import 前试抢，先到的线程还卡在
    # import 里、锁是空的 → 后到的任务会误判「不用排队」，随后静默阻塞在 with 上。
    # 试抢成功必须立刻归还（threading.Lock 不可重入），真正取锁交给下面的 with。
    if on_waiting is not None:
        if _parse_lock.acquire(blocking=False):
            _parse_lock.release()
        else:
            on_waiting()

    # 同步路由排队是预期行为 → 阻塞式 with（慢，但可预测）
    with _parse_lock:
        # T4-2: 已拿到锁、还没解析 —— 「排队中」到此为止，进度切到「解析中」。
        # T3-1: 回调**返回 False** 表示「这个任务在排队期间已被取消」→ 立刻放弃，
        # 位置必须在 `ParserOrchestrator()` 之前，否则白烧一次 docling（约 15 s + 3.5 GB）。
        # 向后兼容：返回 None / 其它值 → 照常解析（同步路由根本不传 on_acquired）。
        if on_acquired is not None and on_acquired() is False:
            raise ParseCancelled("排队期间已取消，未解析", stage="排队期间")

        orchestrator = ParserOrchestrator()
        parsed_result = orchestrator.parse_paper(str(pdf_path))

        # T2-3: 写库前的最后一道闸。docling 是黑盒调用（分钟级、不可中断），
        # 取消只能在这里生效 —— 过了这一行就一定会写库。
        if before_store is not None and before_store():
            raise ParseCancelled("任务已取消，未写库", stage="解析后")

        if not DatabaseWriter().insert_paper(parsed_result):
            raise ParseStoreError("解析成功但写入数据库失败")

        paper_id = parsed_result.get("paper_id", "")
        title = parsed_result.get("metadata", {}).get("title", filename)
        paragraph_count = len(parsed_result.get("paragraphs", []))

    return {
        "paper_id": paper_id,
        "title": title,
        "paragraph_count": paragraph_count,
        "stats": {
            "paragraphs": paragraph_count,
            "figures": len(parsed_result.get("figures", [])),
            "citations": len(parsed_result.get("citations", [])),
        },
    }


@app.route("/api/papers/parse", methods=["POST"])
def parse_local_paper():
    """V25.14: 触发解析一篇本地未解析的 PDF 文献。

    Request body:
      filename: PDF 文件名（在 documents 目录下）

    Returns:
      paper_id, status, title, stats
    """
    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "").strip()

    if not filename:
        return jsonify({"error": "缺少 filename 参数"}), 400

    # 防止路径穿越
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "非法的文件名"}), 400

    pdf_path = DOCUMENTS_DIR / filename
    # T3-6: 入参校验（顺序固定）：后缀 → 是否普通文件。
    # 传目录名时 exists() 为真，会一路到 docling 才炸；传 .txt 也会直接进解析。
    # 无后缀的名字（多为目录名，如 `docs`）归到「不是普通文件」——报 404 比
    # 报「只支持 .pdf」更准确，也与工单 T3-6-a 的判据一致。
    suffix = pdf_path.suffix.lower()
    if suffix != ".pdf":
        if suffix:
            return jsonify({"error": f"只支持 .pdf 文件: {filename}"}), 400
        return jsonify({"error": f"文件不存在或不是普通文件: {filename}"}), 404
    if not pdf_path.is_file():
        return jsonify({"error": f"文件不存在或不是普通文件: {filename}"}), 404

    # T3-3: 本路由**有意不做并发准入**（不是漏了）。前端「解析」按钮是人点的，
    # 加 429 只会让页面莫名报错；并发额度由异步路由 parse_async 兜住。
    # 两条路由共用 _parse_and_store 里的 _parse_lock，不会真并行跑两个 docling。

    # 检查是否已解析。统一口径：段落数多者优先、并列取创建更早的
    # （papers.filename 不唯一，同一文件可能有 `<id>` 与 `<id>_mineru` 两行）
    row = _find_parsed_paper(filename)

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
        # 与异步路由共用同一把锁（_parse_and_store 内部持有），
        # 前端「解析」按钮与 MCP 提交不会再有两次 docling 并发。
        result = _parse_and_store(pdf_path, filename)
    except ParseStoreError:
        # 字段与文案保持原样（前端按 error 展示）
        return jsonify({"error": "解析成功但写入数据库失败"}), 500
    except ImportError as e:
        # 导入失败时给出更明确的诊断；此时尚未取锁，不会卡住队列
        import traceback
        print(f"❌ 解析模块导入失败: {e}")
        traceback.print_exc()
        return jsonify({"error": f"解析模块导入失败: {str(e)}。请确认 build_db/ 目录完整且 docling 已安装（pip install docling）"}), 500
    except Exception as e:
        print(f"❌ 解析失败: {filename} - {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"解析失败: {str(e)}"}), 500

    print(f"✅ 解析完成: {result['title']} ({result['paragraph_count']} 段落)")
    return jsonify({
        "paper_id": result["paper_id"],
        "status": "parsed",
        "title": result["title"],
        "paragraph_count": result["paragraph_count"],
        "stats": result["stats"],
    })


@app.route("/api/papers/parse_async", methods=["POST"])
def parse_local_paper_async():
    """V33.17-6B: 异步解析本地 PDF（立即返回 task_id）。

    参数与同步版 `/api/papers/parse` 完全一致：JSON body 的 `filename`。

    校验顺序（**便宜校验必须在返回 task_id 之前**，让模型立刻知道参数错了）：
      1. `filename` 为空              → 400
      2. 含 `..` / `/` / `\\`         → 400（路径穿越）
      3. 后缀不是 `.pdf`              → 400
      4. 不是普通文件（不存在/是目录）→ 404
      以上四条都在 `create_task()` 之前判掉。
    并发准入（T3-3）：running 的 `parse_paper` 任务达到 `PARSE_MAX_CONCURRENT`（3）
      → **429** + `{error, running, limit}`，且**不建任务行**。不排队、不静默等待。

    后台线程：
      · 已解析（`_find_parsed_paper` 命中，段落数多者优先）→ **秒级**
        `complete_task({"status":"already_parsed", ...})`
      · 未解析 → `_parse_and_store()`（内部持有 `_parse_lock`，与同步路由共用）→
        `complete_task({"status":"parsed", ...})`
      · 失败 → `fail_task(task_id, str(e)[:500])`

    ⚠️ 取消语义（如实说明）：
      **docling 期间无法中断**。取消在三个点生效：
        1. 提交后、拿锁前（`is_cancelled`）；
        2. **拿到锁、还没解析**（T3-1 的 `on_acquired`）—— 排队期间取消的话，
           这里直接放弃，**连 docling 都不跑**（不再白烧一次解析）；
        3. **写库之前**（`_parse_and_store` 的 `before_store`）——
           解析已跑完时取消，仍然不写库。
      若请求到达时已经过了「写库点」，数据会保留、任务可能仍是 `completed`。

    ⚠️ 能力边界（如实告知模型）：
      · 只能解析 `documents/` 下**已存在**的 PDF；本端点**不能上传**文件（MCP 传不了 multipart）。
      · `insert_paper` **不写 ChromaDB** → 解析入库后**不保证立刻被混合检索命中**，
        但可以按 `paper_id` 查到详情、也能进图谱。
      · 任务与 review 任务同表，用 `review_task_status`（`/api/review/task/<id>`）轮询。
    """
    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename", "")).strip()

    # ===== 同步校验（必须在 create_task 之前）=====
    if not filename:
        return jsonify({"error": "缺少 filename 参数"}), 400
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "非法的文件名"}), 400

    pdf_path = DOCUMENTS_DIR / filename
    # T3-6: 与同步路由同一套校验（后缀 → 普通文件），且都在建任务之前。
    # 无后缀 → 404「不是普通文件」；有非 .pdf 后缀 → 400「只支持 .pdf」。
    suffix = pdf_path.suffix.lower()
    if suffix != ".pdf":
        if suffix:
            return jsonify({"error": f"只支持 .pdf 文件: {filename}"}), 400
        return jsonify({"error": f"文件不存在或不是普通文件: {filename}"}), 404
    if not pdf_path.is_file():
        return jsonify({"error": f"文件不存在或不是普通文件: {filename}"}), 404

    # T3-3: 并发准入。「查 running 数」与「create_task」必须在同一把短锁里，
    # 否则两个请求可能同时读到 running=2 都放行。超限**不建任务行**。
    with _parse_admit_lock:
        running = _parse_running_count()
        if running >= PARSE_MAX_CONCURRENT:
            return jsonify({
                "error": f"解析任务已达上限（{PARSE_MAX_CONCURRENT}），请等前面的完成或取消",
                "running": running,
                "limit": PARSE_MAX_CONCURRENT,
            }), 429
        # T3-4: params 落库，方便事后按文件名定位任务（get_task 仍只返回 7 键）
        task_id = task_manager.create_task("parse_paper", params={"filename": filename})

    def _fail(error_text: str) -> None:
        """置 failed，并把 progress 从上一阶段（如「写入数据库…」）改掉。

        V33.17: 必须**先**改 progress 再 fail —— `update_progress` 与 `fail_task`
        都带 `WHERE status='running'`，顺序反了就改不动，前端会看到
        `status=failed | progress=写入数据库…` 这种自相矛盾的组合。
        """
        task_manager.update_progress(task_id, "已失败")
        task_manager.fail_task(task_id, error_text)

    def _on_acquired() -> bool:
        """拿到锁、尚未解析（T3-1）。

        返回 **False** = 排队期间已被取消 → `_parse_and_store` 会在构造
        `ParserOrchestrator()` 之前放弃，**不跑 docling**。
        返回 True = 正常，顺带把 progress 切到「解析中」。
        """
        if task_manager.is_cancelled(task_id):
            return False
        task_manager.update_progress(task_id, "解析中（docling）…")
        return True

    def _before_store() -> bool:
        """写库前的最后一道闸（在 _parse_and_store 的锁内、解析完成后被调用）。

        返回 True = 放弃写库。顺带把 progress 推进到「写入数据库…」——
        此刻任务状态仍是 running，`update_progress` 写得进去。
        """
        if task_manager.is_cancelled(task_id):
            return True
        task_manager.update_progress(task_id, "写入数据库…")
        return False

    def run_task():
        try:
            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            # ── 快路径：已解析，秒级返回（统一口径，见 _find_parsed_paper）──
            row = _find_parsed_paper(filename)
            if row:
                task_manager.complete_task(task_id, {
                    "paper_id": row["paper_id"],
                    "status": "already_parsed",
                    "title": row["title"] or filename,
                    "paragraph_count": row["total_paragraphs"] or 0,
                })
                return

            # ── 慢路径 ──
            if task_manager.is_cancelled(task_id):
                task_manager.cancel_task(task_id)
                return

            # T4-2: 两条进度都由 _parse_and_store 回调写，时机才准：
            #   on_waiting  —— 试抢锁失败（真的要排队）→ 「排队中」
            #   on_acquired —— 真正拿到锁（开始解析）  → 「解析中（docling）…」
            # 以前这里无条件写「解析中」，紧接就阻塞在锁上 → 排队不可观测；
            # 试抢也不能放在路由层：_parse_and_store 里的 docling import 首次要
            # 10~15 秒，那时锁还是空的，会漏报排队。
            result = _parse_and_store(
                pdf_path,
                filename,
                before_store=_before_store,
                on_waiting=lambda: task_manager.update_progress(
                    task_id, "排队中（前面还有解析任务）"
                ),
                on_acquired=_on_acquired,
            )

            task_manager.complete_task(task_id, {
                "paper_id": result["paper_id"],
                "status": "parsed",
                "title": result["title"],
                "paragraph_count": result["paragraph_count"],
                "stats": result["stats"],
            })
        except ParseCancelled as exc:
            # 已取消 → 数据没写库。状态由取消端点置为 cancelled，这里只留日志。
            task_manager.cancel_task(task_id)  # 已是 cancelled 时 rowcount=0，幂等
            # flush=True：进程被 kill 时 stdout 是块缓冲，这行会丢；这条日志是
            # 「取消确实没写库」的唯一现场证据，不能指望缓冲区。
            # T3-1: 阶段由 ParseCancelled.stage 给出（排队期间 / 解析后）
            print(
                f"[INFO] 解析已取消（{exc.stage or '未知阶段'}），未写库："
                f"{filename}（{task_id}）",
                flush=True,
            )
        except ParseStoreError as e:
            _fail(str(e))
        except Exception as e:
            print(f"[ERROR] Async parse failed: {filename} - {e}")
            import traceback
            traceback.print_exc()
            # 不要把整段 traceback 塞进 DB
            _fail(str(e)[:500])

    threading.Thread(target=run_task, daemon=True).start()
    return jsonify({"task_id": task_id})


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
    # V33.17: 函数内局部导入（项目风格）。此前缺失导致 name 'sqlite3' is not defined，
    # 异常被下面 try/except 吞掉，迁移从未真正执行过。
    import sqlite3
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

        # V33.17: 段落 FTS 触发器修复（**既有缺陷**，不是 6-B 引入）。
        # 根因：`build_db/build_fts.py` 曾 DROP TABLE paragraphs_fts 后按 5 列重建
        # （section_l1 / section_l2），但 SQLite 的 DROP TABLE **不连带删触发器** ——
        # 库里 paragraphs_ai/ad/au 仍写 section_level1/2/3，于是 paragraphs 的任何
        # INSERT/UPDATE/DELETE 都报 `no column named section_level1`：
        # 前端「解析」按钮（同步 /api/papers/parse）、6-B 的 parse_async、
        # build_db/dedup_papers.py 的去重 DELETE 全挂。
        #
        # DDL 唯一真源在 build_db/build_fts.py 的 PARAGRAPHS_TRIGGER_DDL，
        # 这里只 import 函数来跑，**不另抄一份**。
        # 判据式检测：触发器插入 paragraphs_fts 的**目标列**与 FTS 表实际列不一致
        # 才重建 → 第二次启动不 DROP、不 CREATE、不打日志（幂等）。
        # 判据实现在 build_fts.paragraphs_triggers_need_fix()，不用
        # `"section_level1" in sql` 那种子串判断（新 DDL 里必然出现
        # `new.section_level1`，会永远判定需要修）。
        # 只碰这 3 个触发器，不动历史数据行、不 rebuild 存量 FTS。
        try:
            from build_db.build_fts import (
                paragraphs_triggers_need_fix,
                rebuild_paragraphs_triggers,
            )

            if paragraphs_triggers_need_fix(cursor):
                rebuild_paragraphs_triggers(cursor)
                conn.commit()
                print("🔧 触发器迁移：paragraphs_ai/ad/au 已按 section_l1|section_l2 重建")
        except Exception as fts_exc:
            # 与整个迁移函数策略一致：失败必须可见，但**不许阻塞启动**
            print(f"⚠️  触发器迁移失败（不影响启动）: {fts_exc}")

        conn.close()
    except Exception as e:
        print(f"⚠️  数据库迁移跳过（不影响运行）: {e}")


# ---------------------------------------------------------------------------
# V33.17-6A: 启动对账（review 僵尸任务收尸）
# ---------------------------------------------------------------------------

# 持久化任务类型白名单（6-A 名为 REVIEW_TASK_TYPES，6-B 加入 parse_paper 后改名）。
# ⚠️ **另一份在 `services/review/task_manager.py` 的 `PERSISTED_TASK_TYPES`，
#    两处值必须完全一致。**
# `download_online` 属于 services/search/online_downloader.py 的另一套任务体系，
# 虽然同表，但**永远不许**进这个白名单。
PERSISTED_TASK_TYPES = (
    "qa_ask",
    "agentic_search",
    "generate_outline",
    "generate_review",
    "parse_paper",
)


def reconcile_stale_review_tasks() -> int:
    """把上次进程遗留的**持久化** `running` 任务收成 `failed`。

    为什么必须做：这些任务（review 4 类 + 6-B 的 `parse_paper`）落 `tasks` 表。
    进程被杀时正在跑的任务会永远停在 `running` —— `/api/review/running_task`
    会一直返回它，前端误以为"还在跑"，新任务也难识别。

    范围**严格限定**在 `PERSISTED_TASK_TYPES`：
        qa_ask / agentic_search / generate_outline / generate_review / parse_paper
    `download_online` 等类型属于 services/search/online_downloader.py 的**另一套**
    任务体系，绝不能在这里被顺手改掉。

    幂等：没有 running 行时 rowcount=0，什么也不做；重复启动不报错。
    返回：被收掉的条数。
    """
    if not DB_PATH.exists():
        return 0

    import sqlite3
    from datetime import datetime

    placeholders = ",".join("?" for _ in PERSISTED_TASK_TYPES)
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        cursor = conn.execute(
            f"UPDATE tasks SET status='failed', error=?, finished_at=? "
            f"WHERE status = 'running' AND type IN ({placeholders})",
            (
                "服务重启导致任务中断",
                datetime.now().isoformat(timespec="seconds"),
                *PERSISTED_TASK_TYPES,
            ),
        )
        conn.commit()
        return cursor.rowcount
    except Exception as exc:
        # 表不存在 / 库被占用等都不许阻塞启动
        print(f"⚠️ 启动对账失败（不影响启动）：{exc}")
        return 0
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("SCIPAL_HOST", "0.0.0.0")
    port = int(os.environ.get("SCIPAL_PORT", "5000"))
    debug = os.environ.get("SCIPAL_DEBUG", "0") == "1"
    print(f"🧪 Sci-Pal API V33.17 — http://{host}:{port}")
    print(f"   DB: {DB_PATH}")
    print(f"   Frontend: {FRONTEND_DIR}")
    run_db_migrations()

    # V33.17-6A: 收掉上次进程遗留的任务。范围 = PERSISTED_TASK_TYPES
    # （6-B 起含 parse_paper，故措辞用「持久化任务」而非「review 任务」）
    _stale = reconcile_stale_review_tasks()
    print(
        f"🧹 启动对账：收掉 {_stale} 个遗留持久化任务（status→failed）"
        if _stale
        else "🧹 启动对账：无遗留持久化任务"
    )

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

    # V33.17 C-2: threaded=True —— 不让一次同步重请求（review/generate、agentic/search、
    # qa/ask）把整站请求循环堵死。安全阀已先就位，顺序不能反：
    #   1) 异步任务每个 new 私有 ReviewGenerator 实例（参数/中间结果不共享）
    #   2) 同步 review/generate 由 _review_generate_lock 串行化（共享单例仍安全）
    app.run(host=host, port=port, debug=debug, threaded=True)
