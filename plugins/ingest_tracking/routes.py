"""Client-only ingest tracking API plugin."""

from __future__ import annotations

import uuid
from typing import Any

from flask import Blueprint, jsonify, request

from . import store

STATUSES = {"clean", "warning", "needs_review", "duplicate", "rejected", "reviewed"}


def _json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def build_ingest_tracking_blueprint(log=None, *, schema_ready=None):
    bp = Blueprint("ingest_tracking", __name__)
    check_schema = schema_ready or store.schema_ready

    @bp.before_request
    def require_schema():
        if not check_schema():
            return jsonify({
                "error": "ingest tracking schema missing; run scripts/migrate_ingest_tracking.py"
            }), 503

    @bp.post("/api/ingest-tracking/batches")
    def create_batch():
        body = _json()
        batch_id = str(body.get("batch_id") or uuid.uuid4().hex)
        store.create_batch(
            batch_id,
            str(body.get("source") or "client"),
            int(body.get("total") or 0),
            body.get("meta") or {},
        )
        return jsonify({"batch_id": batch_id}), 201

    @bp.get("/api/ingest-tracking/batches/<batch_id>")
    def get_batch(batch_id: str):
        batch = store.get_batch(batch_id)
        if not batch:
            return jsonify({"error": "batch not found"}), 404
        return jsonify(batch)

    @bp.post("/api/ingest-tracking/batches/<batch_id>/items")
    def add_item(batch_id: str):
        body = _json()
        status = str(body.get("quality_status") or "clean")
        if status not in STATUSES:
            return jsonify({"error": f"invalid quality_status: {status}"}), 400
        item_id = store.add_item(
            batch_id,
            str(body.get("filename") or ""),
            body.get("paper_id"),
            status,
            body.get("flags") or [],
        )
        for flag in body.get("flags") or []:
            store.add_finding(
                batch_id,
                item_id,
                str(flag.get("code") or "DQ000"),
                str(flag.get("severity") or "warn"),
                str(flag.get("message") or ""),
                flag,
            )
        return jsonify({"item_id": item_id, "quality_status": status}), 201

    @bp.post("/api/ingest-tracking/batches/<batch_id>/finish")
    def finish_batch(batch_id: str):
        store.finish_batch(batch_id, _json())
        batch = store.get_batch(batch_id)
        if not batch:
            return jsonify({"error": "batch not found"}), 404
        return jsonify(batch)

    @bp.get("/api/ingest-tracking/papers/<paper_id>")
    def get_paper(paper_id: str):
        row = store.get_paper(paper_id)
        if not row:
            return jsonify({"error": "paper not found"}), 404
        return jsonify(row)

    @bp.post("/api/ingest-tracking/papers/<paper_id>/review")
    def review_paper(paper_id: str):
        body = _json()
        status = str(body.get("quality_status") or "reviewed")
        if status not in STATUSES:
            return jsonify({"error": f"invalid quality_status: {status}"}), 400
        if not store.review_paper(paper_id, status, body.get("flags")):
            return jsonify({"error": "paper not found"}), 404
        return jsonify({"paper_id": paper_id, "quality_status": status})

    if log is not None:
        log.info("ingest tracking plugin enabled")
    return bp
