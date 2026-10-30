"""Project API scoped to the active workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, session

from services.projects import (
    add_member,
    copy_project,
    create_project,
    get_project,
    list_projects,
    update_project,
)
from services.tenancy import get_membership
from services.tenancy.permissions import audit
from services.tenancy.web import resolve_workspace


def build_projects_blueprint(*, db_path: str | Path, log: Any = None) -> Blueprint:
    bp = Blueprint("projects", __name__)
    db = str(db_path)

    def context():
        user_id = session.get("user_id")
        if not user_id:
            return None, None
        return user_id, resolve_workspace(db_path=db)

    @bp.get("/api/projects")
    def projects_list():
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        return jsonify({"projects": list_projects(workspace_id, user_id, db_path=db)})

    @bp.post("/api/projects")
    def projects_create():
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            project = create_project(
                workspace_id,
                user_id,
                str(body.get("name") or ""),
                str(body.get("description") or ""),
                status=str(body.get("status") or "active"),
                db_path=db,
            )
        except PermissionError:
            return jsonify({"error": "workspace access denied"}), 403
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(project), 201

    @bp.get("/api/projects/<project_id>")
    def projects_detail(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        project = get_project(project_id, workspace_id, user_id, db_path=db)
        if not project:
            return jsonify({"error": "Project not found"}), 404
        membership = get_membership(workspace_id, user_id, db_path=db)
        if membership and membership.role == "pi":
            audit(workspace_id, user_id, "pi.read", target=project_id, db_path=db)
        return jsonify(project)

    @bp.post("/api/projects/<project_id>/copy")
    def projects_copy(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        project = copy_project(project_id, workspace_id, user_id, db_path=db)
        if not project:
            return jsonify({"error": "Project not found or copy denied"}), 404
        return jsonify(project), 201

    @bp.put("/api/projects/<project_id>")
    def projects_update(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            project = update_project(
                project_id,
                workspace_id,
                user_id,
                name=body.get("name"),
                description=body.get("description"),
                status=body.get("status"),
                db_path=db,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not project:
            return jsonify({"error": "Project not found"}), 404
        return jsonify(project)

    @bp.post("/api/projects/<project_id>/members")
    def projects_add_member(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            member = add_member(
                project_id,
                workspace_id,
                user_id,
                str(body.get("user_id") or ""),
                str(body.get("role") or "member"),
                db_path=db,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not member:
            return jsonify({"error": "Project not found or permission denied"}), 404
        return jsonify(member), 201

    return bp
