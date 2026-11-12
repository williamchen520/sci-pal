"""Same-origin proxy for the independent code-rag HTTP service."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from flask import Blueprint, jsonify, request, session

from config.settings import DATABASE_PATH
from services.platform.libraries import get_library
from services.tenancy.service import authorize
from services.tenancy.web import auth_required, resolve_workspace


def build_code_libraries_blueprint(*, db_path: str = str(DATABASE_PATH)) -> Blueprint:
    bp = Blueprint("code_libraries", __name__)
    db = str(db_path)
    base = os.environ.get("SCIPAL_CODE_API_URL", "http://127.0.0.1:5010").rstrip("/")

    def _workspace() -> str | None:
        return resolve_workspace(default=None, db_path=db)

    def _can(workspace_id: str) -> bool:
        user_id = session.get("user_id")
        if not user_id:
            return not auth_required()
        return authorize(user_id, workspace_id, "read_workspace", db_path=db)

    def _library(library_id: str):
        library = get_library(library_id)
        workspace = _workspace()
        if not library or not workspace or library["workspace_id"] != workspace:
            return None, (jsonify({"error": "library not found"}), 404)
        if library["kind"] != "code":
            return None, (jsonify({"error": "not a code library"}), 400)
        if not _can(workspace):
            return None, (jsonify({"error": "workspace access denied"}), 403)
        return library, None

    def _call(method: str, path: str, payload: dict[str, Any] | None = None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_obj = urllib.request.Request(
            base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=60) as response:
                return jsonify(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return jsonify({"error": "code service rejected request", "detail": detail}), 502
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"code service unavailable: {exc}"}), 502

    @bp.get("/api/code/libraries/<library_id>/status")
    def status(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/status")

    @bp.post("/api/code/libraries/<library_id>/search")
    def search(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        body = request.get_json(silent=True) or {}
        if not str(body.get("query") or "").strip():
            return jsonify({"error": "query is required"}), 400
        return _call(
            "POST",
            f"/libraries/{urllib.parse.quote(library_id)}/search",
            {
                "query": str(body.get("query")),
                "top_k": int(body.get("top_k") or 10),
                "snapshot_id": str(body.get("snapshot_id") or ""),
            },
        )

    @bp.get("/api/code/libraries/<library_id>/trace")
    def trace(library_id: str):
        _, error = _library(library_id)
        if error:
            return error
        unit_id = str(request.args.get("unit_id") or "").strip()
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400
        params = urllib.parse.urlencode(
            {
                "unit_id": unit_id,
                "direction": request.args.get("direction") or "both",
                "max_hops": request.args.get("max_hops") or 2,
                "max_nodes": request.args.get("max_nodes") or 30,
            }
        )
        return _call("GET", f"/libraries/{urllib.parse.quote(library_id)}/trace?{params}")

    return bp
