"""Experiment run API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, session

from services.experiments.compare import compare_run_row
from services.experiments.runs import create_run, get_run, list_runs, update_run
from services.tenancy.web import resolve_workspace


def build_runs_blueprint(*, db_path: str | Path, log: Any = None) -> Blueprint:
    bp = Blueprint("experiment_runs", __name__)
    db = str(db_path)

    def context():
        user_id = session.get("user_id")
        if not user_id:
            return None, None
        return user_id, resolve_workspace(db_path=db)

    @bp.get("/api/experiments/<experiment_id>/runs")
    def runs_list(experiment_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        rows = list_runs(experiment_id, workspace_id, user_id, db_path=db)
        if rows is None:
            return jsonify({"error": "Experiment not found"}), 404
        return jsonify({"runs": rows})

    @bp.post("/api/experiments/<experiment_id>/runs")
    def runs_create(experiment_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            row = create_run(
                experiment_id,
                workspace_id,
                user_id,
                str(body.get("title") or ""),
                status=str(body.get("status") or "planned"),
                planned=body.get("planned") or {},
                actual=body.get("actual") or {},
                observations=str(body.get("observations") or ""),
                result=str(body.get("result") or ""),
                db_path=db,
            )
        except PermissionError:
            return jsonify({"error": "Experiment not found"}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(row), 201

    @bp.get("/api/runs/<run_id>")
    def runs_detail(run_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        row = get_run(run_id, workspace_id, user_id, db_path=db)
        if not row:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(row)

    @bp.get("/api/runs/<run_id>/comparison")
    def runs_comparison(run_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        row = get_run(run_id, workspace_id, user_id, db_path=db)
        if not row:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(compare_run_row(row))

    @bp.put("/api/runs/<run_id>")
    def runs_update(run_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            row = update_run(
                run_id,
                workspace_id,
                user_id,
                title=body.get("title"),
                status=body.get("status"),
                planned=body.get("planned"),
                actual=body.get("actual"),
                observations=body.get("observations"),
                result=body.get("result"),
                db_path=db,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not row:
            return jsonify({"error": "Run not found"}), 404
        return jsonify(row)

    return bp
