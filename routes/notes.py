"""Personal notes API, scoped to the active workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, session

from services.notes.service import create_note, delete_note, list_notes, update_note
from services.tenancy.web import resolve_workspace


def build_notes_blueprint(*, db_path: str | Path, log: Any = None) -> Blueprint:
    bp = Blueprint("notes", __name__)
    db = str(db_path)

    def context():
        user_id = session.get("user_id")
        if not user_id:
            return None, None
        return user_id, resolve_workspace(db_path=db)

    @bp.get("/api/notes")
    def notes_list():
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        paper_id = request.args.get("paper_id") or None
        return jsonify({"notes": list_notes(workspace_id, user_id, paper_id=paper_id, db_path=db)})

    @bp.post("/api/notes")
    def notes_create():
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            note = create_note(
                workspace_id,
                user_id,
                str(body.get("content") or ""),
                paper_id=body.get("paper_id") or None,
                para_id=body.get("para_id") or None,
                db_path=db,
            )
        except PermissionError:
            return jsonify({"error": "Paper not found"}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(note), 201

    @bp.put("/api/notes/<note_id>")
    def notes_update(note_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        body = request.get_json(silent=True) or {}
        try:
            note = update_note(note_id, workspace_id, user_id, str(body.get("content") or ""), db_path=db)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if not note:
            return jsonify({"error": "Note not found"}), 404
        return jsonify(note)

    @bp.delete("/api/notes/<note_id>")
    def notes_delete(note_id: str):
        user_id, workspace_id = context()
        if not user_id:
            return jsonify({"error": "authentication required"}), 401
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 403
        if not delete_note(note_id, workspace_id, user_id, db_path=db):
            return jsonify({"error": "Note not found"}), 404
        return jsonify({"ok": True})

    return bp
