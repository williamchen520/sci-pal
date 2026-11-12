"""Platform library registry API."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request, session

from services.platform.libraries import (
    LibraryError,
    create_library,
    delete_library,
    get_library,
    list_libraries,
)
from services.tenancy.service import authorize
from services.tenancy.web import auth_required, resolve_workspace
from config.settings import DATABASE_PATH


def build_libraries_blueprint(*, db_path: str = str(DATABASE_PATH)) -> Blueprint:
    bp = Blueprint("libraries", __name__)
    db = str(db_path)

    def _user_id() -> str | None:
        return session.get("user_id")

    def _workspace() -> str | None:
        return resolve_workspace(default=None, db_path=db)

    def _can(workspace_id: str, action: str) -> bool:
        user_id = _user_id()
        if not user_id:
            return not auth_required()
        return authorize(user_id, workspace_id, action, db_path=db)

    def _error(message: str, status: int = 400):
        return jsonify({"error": message}), status

    @bp.get("/api/libraries")
    def list_all():
        workspace_id = _workspace()
        if not workspace_id:
            return _error("workspace required", 401)
        if not _can(workspace_id, "read_workspace"):
            return _error("workspace access denied", 403)
        kind = (request.args.get("kind") or "").strip() or None
        return jsonify({"libraries": list_libraries(workspace_id=workspace_id, kind=kind)})

    @bp.post("/api/libraries")
    def create():
        workspace_id = _workspace()
        if not workspace_id:
            return _error("workspace required", 401)
        if not _can(workspace_id, "write_own"):
            return _error("workspace write denied", 403)
        user_id = _user_id()
        if not user_id:
            return _error("authentication required", 401)
        body = request.get_json(silent=True) or {}
        kind = str(body.get("kind") or "").strip()
        config: dict[str, Any] = body.get("config") or {}
        if kind == "code" and not str(config.get("repo_url") or "").strip():
            return _error("code library requires config.repo_url")
        try:
            library = create_library(
                owner_user_id=user_id,
                workspace_id=workspace_id,
                kind=kind,
                name=str(body.get("name") or ""),
                module_id=body.get("module_id"),
                visibility=str(body.get("visibility") or "private"),
                config=config,
            )
        except LibraryError as exc:
            return _error(str(exc), 400)
        return jsonify(library), 201

    @bp.get("/api/libraries/<library_id>")
    def detail(library_id: str):
        workspace_id = _workspace()
        if not workspace_id:
            return _error("workspace required", 401)
        if not _can(workspace_id, "read_workspace"):
            return _error("workspace access denied", 403)
        library = get_library(library_id)
        if not library or library["workspace_id"] != workspace_id:
            return _error("library not found", 404)
        return jsonify(library)

    @bp.delete("/api/libraries/<library_id>")
    def remove(library_id: str):
        workspace_id = _workspace()
        if not workspace_id:
            return _error("workspace required", 401)
        if not _can(workspace_id, "write_workspace"):
            return _error("workspace management denied", 403)
        library = get_library(library_id)
        if not library or library["workspace_id"] != workspace_id:
            return _error("library not found", 404)
        delete_library(library_id)
        return jsonify({"ok": True, "library_id": library_id})

    return bp
