"""Reviews read-only routes: durable review lookup from ``research.db``.

The web API historically served citation tracing from the in-process
``ReviewStore`` only, so reviews produced by the CLI (or an external client)
were invisible to the frontend. These routes read the ``reviews`` table written
by the workflow's store stage.

Response shape follows the ``contracts`` envelope (new routes only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from contracts import InternalError, NotFound, fail, ok
from services.review.review_repository import ReviewRepository


def build_reviews_blueprint(
    *,
    db_path: Path,
    log: Any,
    get_task_manager: Any = None,
    get_review_store: Any = None,
    get_llm_client: Any = None,
) -> Blueprint:
    bp = Blueprint("reviews", __name__, url_prefix="/api")

    @bp.get("/reviews")
    def list_reviews():
        limit = _int_arg("limit", 20, minimum=1, maximum=100)
        try:
            records = ReviewRepository(db_path).list(limit=limit)
        except Exception:
            log.exception("list_reviews failed")
            error = InternalError("Failed to list reviews")
            return jsonify(fail(error)), error.status

        summaries = [
            {key: value for key, value in record.items() if key != "markdown"}
            for record in records
        ]
        return jsonify(ok({"count": len(summaries), "reviews": summaries}))

    @bp.get("/reviews/<review_id>")
    def get_review(review_id: str):
        try:
            record = ReviewRepository(db_path).get(review_id)
        except Exception:
            log.exception("get_review failed")
            error = InternalError("Failed to load review")
            return jsonify(fail(error)), error.status

        if record is None:
            error = NotFound(f"Review not found: {review_id}")
            return jsonify(fail(error)), error.status
        return jsonify(ok(record))

    # ------------------------------------------------- review task / store
    @bp.get("/review/running_task")
    def review_running_task():
        if get_task_manager is None:
            return jsonify({"running": False})
        task = get_task_manager().get_running_task()
        if not task:
            return jsonify({"running": False})
        return jsonify({"running": True, "task": task})

    @bp.get("/review/task/<task_id>")
    def review_task(task_id: str):
        if get_task_manager is None:
            return jsonify({"error": "Task not found"}), 404
        task = get_task_manager().get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    @bp.post("/review/cancel/<task_id>")
    def review_cancel(task_id: str):
        if get_task_manager is None:
            return jsonify({"error": "Task not found or already finished"}), 404
        if not get_task_manager().cancel_task(task_id):
            return jsonify({"error": "Task not found or already finished"}), 404
        return jsonify({"success": True, "message": "Task cancelled"})

    @bp.get("/review/llm_status")
    def review_llm_status():
        if get_llm_client is None:
            return jsonify(fail(InternalError("LLM client not configured"))), 500
        try:
            llm = get_llm_client()
            available = llm.is_available()
            models = llm.list_models() if available else []
            provider = llm.provider
            if provider == "openai":
                hint = None if available else "配置 API key: export SCIPAL_LLM_API_KEY=sk-你的key"
            else:
                hint = None if available else "Start Ollama: ollama serve && ollama pull qwen2.5:14b"
            return jsonify(
                ok(
                    {
                        "available": available,
                        "provider": provider,
                        "configured_model": llm.model,
                        "installed_models": models,
                        "hint": hint,
                    }
                )
            )
        except Exception:
            log.exception("review_llm_status failed")
            error = InternalError("LLM status check failed")
            return jsonify(fail(error)), error.status

    @bp.get("/review/<review_id>")
    def review_detail(review_id: str):
        if get_review_store is None:
            return jsonify({"error": "Review not found or expired"}), 404
        entry = get_review_store().get(review_id)
        if entry is None:
            return jsonify({"error": "Review not found or expired"}), 404
        return jsonify(entry)

    @bp.get("/review/<review_id>/sentence/<sentence_id>")
    def review_sentence(review_id: str, sentence_id: str):
        if get_review_store is None:
            return jsonify({"error": "Sentence not found"}), 404
        result = get_review_store().get_sentence(review_id, sentence_id)
        if result is None:
            return jsonify({"error": "Sentence not found"}), 404
        return jsonify(result)

    return bp


def _int_arg(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))
