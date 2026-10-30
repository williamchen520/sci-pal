"""Online-download read-only routes (status / history / queue).

Pure relocation from ``api_server.py``; response shapes are unchanged so the
frontend and the MCP bridge keep working. The task manager is injected so the
blueprint can be tested without the download subsystem.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from config.settings import DATABASE_PATH
from services.tenancy.scoping import allowed_paper_ids, filter_items
from services.tenancy.web import resolve_workspace


def build_search_blueprint(
    *,
    get_task_manager: Callable[[], Any],
    log: Any,
    get_hybrid_retriever: Callable[[], Any] | None = None,
    db_path: str | None = None,
) -> Blueprint:
    bp = Blueprint("search", __name__, url_prefix="/api")

    @bp.route("/search/hybrid", methods=["GET", "POST"])
    def hybrid_search():
        if get_hybrid_retriever is None:
            return jsonify({"error": "混合检索器未配置"}), 501
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
        workspace_id = resolve_workspace(db_path=db_path or DATABASE_PATH)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        try:
            result = get_hybrid_retriever().search_papers(
                query=query,
                top_k=top_k,
                use_online=use_online,
                online_max_results=online_max,
            )
            allowed = allowed_paper_ids(workspace_id, db_path=db_path or DATABASE_PATH)
            result["local_papers"] = filter_items(result.get("local_papers") or [], allowed)
            result["papers"] = [
                item
                for item in result.get("papers") or []
                if item.get("source") != "local" or item.get("paper_id") in allowed
            ]
            result["local_count"] = len(result["local_papers"])
            result["total"] = len(result["papers"])
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("hybrid search failed")
            return jsonify({"error": f"混合搜索失败: {str(exc)}"}), 500

    @bp.route("/search/online", methods=["GET", "POST"])
    def online_search():
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

            results = get_online_searcher().search(
                query,
                max_results=max_results,
                search_pubmed=search_pubmed,
                search_pmc=search_pmc,
            )
            pubmed_count = sum(1 for r in results if r.source == "online_pubmed")
            pmc_count = sum(1 for r in results if r.source == "online_pmc")
            return jsonify(
                {
                    "query": query,
                    "total": len(results),
                    "pubmed_count": pubmed_count,
                    "pmc_count": pmc_count,
                    "papers": [r.to_dict() for r in results],
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("online search failed")
            return jsonify({"error": f"在线搜索失败: {str(exc)}"}), 500

    @bp.get("/search/download_status")
    def download_status():
        task_id = request.args.get("task_id", "").strip()
        if not task_id:
            return jsonify({"error": "缺少 task_id 参数"}), 400

        try:
            manager = get_task_manager()
            task = manager.get_task(task_id)
            if task is None:
                return jsonify({"error": f"任务不存在: {task_id}"}), 404
            return jsonify(task.to_dict())
        except Exception:
            log.exception("download_status failed")
            return jsonify({"error": "查询任务状态失败"}), 500

    @bp.get("/search/download_history")
    def download_history():
        limit = min(int(request.args.get("limit", 20)), 50)

        try:
            manager = get_task_manager()
            tasks = manager.list_tasks(limit=limit)
            queue_status = manager.get_queue_status()
            return jsonify(
                {"tasks": tasks, "total": len(tasks), "queue_status": queue_status}
            )
        except Exception:
            log.exception("download_history failed")
            return jsonify({"error": "获取下载历史失败"}), 500

    @bp.get("/search/download_queue")
    def download_queue_status():
        try:
            manager = get_task_manager()
            queue_status = manager.get_queue_status()

            current_task = None
            if queue_status["current_task_id"]:
                task = manager.get_task(queue_status["current_task_id"])
                if task:
                    current_task = task.to_dict()

            return jsonify({**queue_status, "current_task": current_task})
        except Exception:
            log.exception("download_queue failed")
            return jsonify({"error": "获取队列状态失败"}), 500

    return bp
