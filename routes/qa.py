"""RAG QA and agentic search routes (moved out of api_server.py)."""

from __future__ import annotations

import threading
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.tenancy.scoping import allowed_paper_ids
from services.tenancy.web import resolve_workspace


def build_qa_blueprint(
    *,
    get_qa_service: Callable[[], Any],
    get_retriever: Callable[[], Any],
    get_task_manager: Callable[[], Any],
    db_path: str | None = None,
) -> Blueprint:
    from config.settings import DATABASE_PATH

    db = db_path or DATABASE_PATH
    bp = Blueprint("qa", __name__)

    @bp.route("/api/qa/ask", methods=["POST"])
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
        workspace_id = resolve_workspace(db_path=db)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        if paper_id and paper_id not in allowed_paper_ids(workspace_id, db_path=db):
            return jsonify({"error": "Paper not found"}), 404

        try:
            qa = get_qa_service()
            result = qa.ask(
                question=question,
                paper_id=paper_id,
                include_diagnostics=include_diagnostics,
                workspace_id=workspace_id,
            )
            return jsonify(result)
        except Exception as e:
            print(f"[ERROR] Q&A failed: {e}")
            return jsonify({"error": f"问答失败: {str(e)}"}), 500


    @bp.route("/api/qa/ask_async", methods=["POST"])
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
        workspace_id = resolve_workspace(db_path=db)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        if paper_id and paper_id not in allowed_paper_ids(workspace_id, db_path=db):
            return jsonify({"error": "Paper not found"}), 404

        task_id = get_task_manager().create_task("qa_ask")

        def run_task():
            try:
                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                qa = get_qa_service()
                get_task_manager().update_progress(task_id, "检索证据并生成回答（不可中断）...")
                result = qa.ask(
                    question=question,
                    paper_id=paper_id,
                    include_diagnostics=include_diagnostics,
                    workspace_id=workspace_id,
                )

                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                get_task_manager().update_progress(task_id, "整理结果...")
                get_task_manager().complete_task(task_id, result)
            except Exception as e:
                print(f"[ERROR] Async Q&A failed: {e}")
                get_task_manager().fail_task(task_id, str(e))

        threading.Thread(target=run_task, daemon=True).start()
        return jsonify({"task_id": task_id})


    @bp.route("/api/qa/status", methods=["GET"])
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


    @bp.route("/api/agentic/search", methods=["GET", "POST"])
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


    @bp.route("/api/agentic/search_async", methods=["POST"])
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

        task_id = get_task_manager().create_task("agentic_search")

        def run_task():
            try:
                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                from services.search.agentic_search import AgenticSearcher

                # E-1 后的写法：注入共享检索器，不再每次请求重建检索栈
                agentic = AgenticSearcher(
                    retriever=get_retriever(),
                    max_hops=max_hops,
                    min_coverage=min_coverage,
                )
                get_task_manager().update_progress(task_id, "执行多跳检索（不可中断）...")
                result = agentic.search(q, paper_id=paper_id, top_paragraphs=top_paragraphs)

                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                get_task_manager().update_progress(task_id, "整理结果...")
                get_task_manager().complete_task(task_id, result)
            except Exception as e:
                print(f"[ERROR] Async agentic search failed: {e}")
                get_task_manager().fail_task(task_id, str(e))

        threading.Thread(target=run_task, daemon=True).start()
        return jsonify({"task_id": task_id})

    return bp
