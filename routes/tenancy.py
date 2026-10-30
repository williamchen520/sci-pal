"""Local account, workspace and membership API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, session

from services.tenancy import (
    ACTIONS,
    ROLE_PERMISSIONS,
    TenancyError,
    add_member,
    authenticate,
    authorize,
    create_workspace,
    get_membership,
    get_user_by_username,
    list_members,
    list_workspaces,
)


def build_tenancy_blueprint(*, db_path: str | Path, log: Any = None) -> Blueprint:
    bp = Blueprint("tenancy", __name__)
    db = str(db_path)

    def current_user_id() -> str | None:
        return session.get("user_id")

    def error(message: str, status: int = 400):
        return jsonify({"error": message}), status

    @bp.post("/api/auth/login")
    def login():
        body = request.get_json(silent=True) or {}
        user = authenticate(str(body.get("username") or ""), str(body.get("password") or ""), db_path=db)
        if not user:
            return error("invalid username or password", 401)
        session.clear()
        session["user_id"] = user["user_id"]
        session.permanent = False
        return jsonify({"user": user, "workspaces": list_workspaces(user["user_id"], db_path=db)})

    @bp.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    @bp.get("/api/auth/me")
    def me():
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        return jsonify({"user_id": user_id, "workspaces": list_workspaces(user_id, db_path=db)})

    @bp.get("/api/workspaces")
    def workspaces():
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        return jsonify({"workspaces": list_workspaces(user_id, db_path=db)})

    @bp.post("/api/workspaces")
    def create():
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        body = request.get_json(silent=True) or {}
        try:
            workspace = create_workspace(str(body.get("name") or ""), user_id, db_path=db)
        except TenancyError as exc:
            return error(str(exc), 400)
        return jsonify(workspace), 201

    @bp.get("/api/workspaces/<workspace_id>/members")
    def members(workspace_id: str):
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        if not authorize(user_id, workspace_id, "read_workspace", db_path=db):
            return error("workspace access denied", 403)
        return jsonify({"members": list_members(workspace_id, db_path=db)})

    @bp.post("/api/workspaces/<workspace_id>/members")
    def add(workspace_id: str):
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        if not authorize(user_id, workspace_id, "manage_members", db_path=db):
            return error("workspace management denied", 403)
        body = request.get_json(silent=True) or {}
        username = str(body.get("username") or "").strip()
        role = str(body.get("role") or "member")
        target = get_user_by_username(username, db_path=db)
        if not target:
            return error("user not found", 404)
        try:
            membership = add_member(workspace_id, target["user_id"], role, actor_user_id=user_id, db_path=db)
        except TenancyError as exc:
            return error(str(exc), 400)
        return jsonify(
            {
                "workspace_id": membership.workspace_id,
                "user_id": membership.user_id,
                "role": membership.role,
                "status": membership.status,
            }
        ), 201

    @bp.get("/api/workspaces/<workspace_id>/role")
    def role(workspace_id: str):
        user_id = current_user_id()
        if not user_id:
            return error("authentication required", 401)
        membership = get_membership(workspace_id, user_id, db_path=db)
        if not membership:
            return error("workspace access denied", 403)
        return jsonify(
            {
                "workspace_id": membership.workspace_id,
                "role": membership.role,
                "actions": sorted(set(ACTIONS) & ROLE_PERMISSIONS[membership.role]),
            }
        )

    return bp
