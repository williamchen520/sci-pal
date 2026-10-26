"""Async ingest routes: submit returns a task_id immediately, status is polled.

Kept separate from ``api_server`` so the service can be injected in tests.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_ingest_blueprint(*, get_service: Callable[[], Any], log: Any) -> Blueprint:
    bp = Blueprint("ingest", __name__, url_prefix="/api")

    @bp.post("/ingest")
    def start_ingest():
        body = request.get_json(silent=True) or {}
        pmc_ids = body.get("pmc_ids") or []
        if not isinstance(pmc_ids, list) or not pmc_ids:
            return jsonify({"ok": False, "error": "pmc_ids must be a non-empty list"}), 400
        try:
            task_id = get_service().start(pmc_ids, batch_size=body.get("batch_size"))
        except (TypeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "task_id": task_id}), 202

    @bp.get("/ingest/<task_id>")
    def ingest_status(task_id: str):
        task = get_service().status(task_id)
        if task is None:
            return jsonify({"ok": False, "error": "task not found"}), 404
        return jsonify({"ok": True, "task": task})

    @bp.post("/ingest/<task_id>/cancel")
    def cancel_ingest(task_id: str):
        if not get_service().cancel(task_id):
            return jsonify({"ok": False, "error": "task not found"}), 404
        return jsonify({"ok": True, "task_id": task_id})

    return bp
