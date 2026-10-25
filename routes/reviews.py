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


def build_reviews_blueprint(*, db_path: Path, log: Any) -> Blueprint:
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

    return bp


def _int_arg(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))
