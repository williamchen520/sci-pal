"""Online-download read-only routes (status / history / queue).

Pure relocation from ``api_server.py``; response shapes are unchanged so the
frontend and the MCP bridge keep working. The task manager is injected so the
blueprint can be tested without the download subsystem.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_search_blueprint(
    *,
    get_task_manager: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("search", __name__, url_prefix="/api")

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
