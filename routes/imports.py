"""Single-tenant import session API."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from services.imports import session as import_session
from services.imports.code_lane import CodeLaneAdapter
from services.imports.orchestrator import process_import
from services.imports.paper_lane import PaperLaneAdapter
from services.tenancy.context import context_from_env
from services.tenancy.web import auth_required


def build_imports_blueprint() -> Blueprint:
    bp = Blueprint("imports", __name__)

    def _tenant() -> str:
        return context_from_env().tenant_id

    def _allowed() -> bool:
        return bool(session.get("user_id")) or not auth_required()

    @bp.post("/api/imports")
    def create_import():
        if not _allowed():
            return jsonify({"error": "login required"}), 401
        payload = request.get_json(silent=True) or {}
        try:
            result = import_session.create_import(
                tenant_id=_tenant(),
                library_id=str(payload.get("library_id") or ""),
                origin=str(payload.get("origin") or "manual"),
                items=payload.get("items") or [],
                created_by=str(session.get("user_id") or ""),
            )
        except import_session.ImportSessionError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(result), 201

    @bp.post("/api/imports/<import_id>/process")
    def process_import_route(import_id: str):
        if not _allowed():
            return jsonify({"error": "login required"}), 401
        try:
            current = import_session.get_import(import_id)
            if current.get("tenant_id") != _tenant():
                return jsonify({"error": "import not found"}), 404
            result = process_import(
                import_id,
                paper_adapter=PaperLaneAdapter(build=True),
                code_adapter=CodeLaneAdapter(),
            )
        except import_session.ImportSessionError:
            return jsonify({"error": "import not found"}), 404
        return jsonify(result)

    @bp.get("/api/imports/<import_id>")
    def get_import(import_id: str):
        if not _allowed():
            return jsonify({"error": "login required"}), 401
        try:
            result = import_session.get_import(import_id)
        except import_session.ImportSessionError:
            return jsonify({"error": "import not found"}), 404
        if result.get("tenant_id") != _tenant():
            return jsonify({"error": "import not found"}), 404
        return jsonify(result)

    @bp.get("/api/imports/<import_id>/items")
    def get_items(import_id: str):
        if not _allowed():
            return jsonify({"error": "login required"}), 401
        try:
            result = import_session.get_import(import_id)
        except import_session.ImportSessionError:
            return jsonify({"error": "import not found"}), 404
        if result.get("tenant_id") != _tenant():
            return jsonify({"error": "import not found"}), 404
        return jsonify({"import_id": import_id, "items": result["items"]})

    @bp.post("/api/imports/<import_id>/retry")
    def retry_import(import_id: str):
        if not _allowed():
            return jsonify({"error": "login required"}), 401
        try:
            result = import_session.retry_items(import_id)
        except import_session.ImportSessionError:
            return jsonify({"error": "import not found"}), 404
        if result.get("tenant_id") != _tenant():
            return jsonify({"error": "import not found"}), 404
        return jsonify(result)

    return bp
