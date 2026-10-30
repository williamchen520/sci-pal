"""Experiment records API: owner-private within a project/workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, session

from services.experiments import (
    create_experiment,
    get_experiment,
    list_experiments,
    update_experiment,
)
from services.tenancy.web import resolve_workspace


def build_experiments_blueprint(*, db_path: str | Path, log: Any = None) -> Blueprint:
    bp = Blueprint("experiments", __name__)
    db = str(db_path)

    def context():
        user_id = session.get("user_id")
        if not user_id:
            return None, None
        return user_id, resolve_workspace(db_path=db)

    @bp.get("/api/projects/<project_id>/experiments")
    def experiments_list(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        rows = list_experiments(project_id, workspace_id, user_id, db_path=db)
        if rows is None:
            return jsonify({"error": "Project not found"}), 404
        return jsonify({"experiments": rows})

    @bp.post("/api/projects/<project_id>/experiments")
    def experiments_create(project_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            row = create_experiment(
                project_id,
                workspace_id,
                user_id,
                str(body.get("title") or ""),
                status=str(body.get("status") or "planned"),
                protocol_id=body.get("protocol_id") or None,
                protocol_version=body.get("protocol_version") or None,
                content=str(body.get("content") or ""),
                db_path=db,
            )
        except PermissionError:
            return jsonify({"error": "Project not found"}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(row), 201

    @bp.get("/api/experiments/<experiment_id>")
    def experiments_detail(experiment_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        row = get_experiment(experiment_id, workspace_id, user_id, db_path=db)
        if not row:
            return jsonify({"error": "Experiment not found"}), 404
        return jsonify(row)

    @bp.put("/api/experiments/<experiment_id>")
    def experiments_update(experiment_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            row = update_experiment(
                experiment_id,
                workspace_id,
                user_id,
                title=body.get("title"),
                status=body.get("status"),
                content=body.get("content"),
                db_path=db,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not row:
            return jsonify({"error": "Experiment not found"}), 404
        return jsonify(row)

    return bp
