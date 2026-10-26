"""Unified-task read routes (list / detail / SSE), extracted from api_server."""

from __future__ import annotations

import json
from typing import Any, Callable

from flask import Blueprint, Response, jsonify, request


def build_tasks_blueprint(
    *,
    list_tasks: Callable[..., list],
    get_task: Callable[[str], Any],
    subscribe: Callable[[str], Any],
) -> Blueprint:
    bp = Blueprint("tasks", __name__, url_prefix="/api")

    @bp.get("/tasks")
    def list_all():
        task_type = request.args.get("type")
        status = request.args.get("status")
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 200))
        except (TypeError, ValueError):
            limit = 50
        tasks = list_tasks(task_type=task_type, status=status, limit=limit)
        return jsonify({"tasks": tasks, "count": len(tasks)})

    @bp.get("/tasks/<task_id>")
    def detail(task_id: str):
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        return jsonify(task)

    @bp.get("/tasks/<task_id>/events")
    def events(task_id: str):
        def generate():
            for event, data in subscribe(task_id):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        return Response(generate(), mimetype="text/event-stream")

    return bp
