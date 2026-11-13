"""Read-only RAG control plane API (R0)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from services.rag_control.registry import check_health, get_provider, list_providers


def build_rag_control_blueprint() -> Blueprint:
    bp = Blueprint("rag_control", __name__)

    @bp.get("/api/rag/providers")
    def providers():
        return jsonify({"providers": list_providers()})

    @bp.get("/api/rag/providers/<rag_id>")
    def provider(rag_id: str):
        value = get_provider(rag_id)
        if not value:
            return jsonify({"error": "provider not found"}), 404
        return jsonify(value)

    @bp.get("/api/rag/providers/<rag_id>/health")
    def health(rag_id: str):
        value = check_health(rag_id)
        if not value:
            return jsonify({"error": "provider not found"}), 404
        return jsonify(value)

    return bp
