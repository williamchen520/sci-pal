"""Async ingest routes: submit returns a task_id immediately, status is polled.

Kept separate from ``api_server`` so the service can be injected in tests.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_ingest_blueprint(
    *,
    get_service: Callable[[], Any],
    log: Any,
    embed_rows: Callable[[list[dict[str, Any]]], int] | None = None,
) -> Blueprint:
    bp = Blueprint("ingest", __name__, url_prefix="/api")

    @bp.post("/embed")
    def embed():
        """Single-writer bridge: the worker posts paragraphs, Flask owns Chroma."""
        if embed_rows is None:
            return jsonify({"ok": False, "error": "embedding disabled"}), 503
        body = request.get_json(silent=True) or {}
        rows = body.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return jsonify({"ok": False, "error": "rows must be a non-empty list"}), 400
        if len(rows) > 256:
            return jsonify({"ok": False, "error": "too many rows (max 256)"}), 400
        try:
            count = embed_rows(rows)
        except Exception as exc:  # noqa: BLE001
            log.exception("embed failed")
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, "count": count})

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
