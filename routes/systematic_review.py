"""Systematic review routes: project, screening, PRISMA, evidence table."""

from __future__ import annotations

import sqlite3

from flask import Blueprint, Response, g, jsonify, request

from services.review import kappa as kappa_mod
from services.review import pico, systematic


def build_systematic_review_blueprint(*, db_path, log) -> Blueprint:
    bp = Blueprint("review_projects", __name__, url_prefix="/api/review-projects")

    def _owner() -> str:
        return getattr(g, "owner", "default")

    def _conn():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @bp.route("", methods=["GET", "POST"])
    def projects():
        conn = _conn()
        try:
            if request.method == "GET":
                return jsonify({"projects": systematic.list_projects(conn, _owner())})
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            project_id = systematic.create_project(
                conn, name, data.get("field_text", ""), data.get("pico") or {},
                owner=_owner(),
            )
            return jsonify({"project_id": project_id}), 201
        finally:
            conn.close()

    @bp.route("/<project_id>", methods=["GET"])
    def project(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not row or row.get("owner") != _owner():
                return jsonify({"error": "project not found"}), 404
            return jsonify(row)
        finally:
            conn.close()

    @bp.route("/<project_id>/papers", methods=["POST"])
    def papers(project_id: str):
        conn = _conn()
        try:
            project_row = systematic.get_project(conn, project_id)
            if not project_row or project_row.get("owner") != _owner():
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            paper_ids = data.get("paper_ids") or []
            systematic.add_papers(conn, project_id, paper_ids)
            return jsonify({"added": len(paper_ids)})
        finally:
            conn.close()

    @bp.route("/<project_id>/screen", methods=["POST"])
    def screen(project_id: str):
        conn = _conn()
        try:
            data = request.get_json(silent=True) or {}
            if not data.get("paper_id") or not data.get("decision"):
                return jsonify({"error": "paper_id and decision required"}), 400
            systematic.screen(
                conn,
                project_id,
                data["paper_id"],
                data["decision"],
                data.get("reason", ""),
                data.get("reviewer", ""),
                data.get("stage", "title_abstract"),
            )
            return jsonify(systematic.prisma(conn, project_id))
        finally:
            conn.close()

    @bp.route("/<project_id>/prisma", methods=["GET"])
    def prisma(project_id: str):
        conn = _conn()
        try:
            return jsonify(systematic.prisma(conn, project_id))
        finally:
            conn.close()

    @bp.route("/<project_id>/evidence", methods=["GET", "POST"])
    def evidence(project_id: str):
        conn = _conn()
        try:
            if request.method == "GET":
                return jsonify({"rows": systematic.list_evidence(conn, project_id)})
            project_row = systematic.get_project(conn, project_id)
            if not project_row:
                return jsonify({"error": "project not found"}), 404
            papers = conn.execute(
                "SELECT p.paper_id, p.title, p.abstract FROM review_project_papers rp "
                "JOIN papers p ON p.paper_id = rp.paper_id WHERE rp.project_id = ?",
                (project_id,),
            ).fetchall()
            added = 0
            for paper in papers:
                row = systematic.extract_evidence(dict(paper), project_row.get("pico"))
                systematic.add_evidence(conn, project_id, paper["paper_id"], row)
                added += 1
            return jsonify({"added": added, "rows": systematic.list_evidence(conn, project_id)})
        finally:
            conn.close()

    @bp.route("/<project_id>/evidence.csv", methods=["GET"])
    def evidence_csv(project_id: str):
        conn = _conn()
        try:
            return Response(
                systematic.evidence_csv(conn, project_id),
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}_evidence.csv"
                },
            )
        finally:
            conn.close()

    @bp.route("/<project_id>/pico", methods=["POST"])
    def extract_pico(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not row or row.get("owner") != _owner():
                return jsonify({"error": "project not found"}), 404
            return jsonify(pico.auto_pico(conn, project_id))
        finally:
            conn.close()

    @bp.route("/<project_id>/kappa", methods=["GET"])
    def screening_kappa(project_id: str):
        conn = _conn()
        try:
            return jsonify(kappa_mod.kappa(conn, project_id))
        finally:
            conn.close()

    return bp
