"""Systematic review routes: project, screening, PRISMA, evidence table."""

from __future__ import annotations

import json
import sqlite3

from flask import Blueprint, Response, g, jsonify, request

from services.review import brief as brief_mod
from services.review import export as export_mod
from services.review import kappa as kappa_mod
from services.review import pdf_report
from services.review import prisma_svg
from services.review import report as report_mod
from services.review import risk_of_bias
from services.review import pico, systematic


def build_systematic_review_blueprint(*, db_path, log) -> Blueprint:
    bp = Blueprint("review_projects", __name__, url_prefix="/api/review-projects")

    def _owner() -> str:
        return getattr(g, "owner", "default")

    def _audit(conn, project_id, action, target="", detail=""):
        systematic.log_event(conn, project_id, _owner(), action, target, detail)

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
            _audit(conn, project_id, "project_created", project_id, name)
            return jsonify({"project_id": project_id}), 201
        finally:
            conn.close()

    @bp.route("/<project_id>", methods=["GET"])
    def project(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            return jsonify(row)
        finally:
            conn.close()

    @bp.route("/<project_id>/papers", methods=["POST"])
    def papers(project_id: str):
        conn = _conn()
        try:
            project_row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            paper_ids = data.get("paper_ids") or []
            systematic.add_papers(conn, project_id, paper_ids)
            _audit(conn, project_id, "papers_added", "", str(len(paper_ids)))
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
            _audit(conn, project_id, "screened", data["paper_id"], data["decision"])
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
            if not project_row or not systematic.can_access(conn, project_id, _owner()):
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
            _audit(conn, project_id, "evidence_extracted", "", str(added))
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
            if not systematic.can_access(conn, project_id, _owner()):
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

    @bp.route("/<project_id>/prisma.svg", methods=["GET"])
    def prisma_diagram(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not row:
                return jsonify({"error": "project not found"}), 404
            counts = systematic.prisma(conn, project_id)
            svg = prisma_svg.render(row.get("name") or project_id, counts)
            return Response(svg, mimetype="image/svg+xml")
        finally:
            conn.close()

    @bp.route("/<project_id>/risk-of-bias", methods=["GET", "POST"])
    def rob(project_id: str):
        conn = _conn()
        try:
            if request.method == "POST":
                papers = conn.execute(
                    "SELECT p.paper_id, p.title, p.abstract FROM review_project_papers rp "
                    "JOIN papers p ON p.paper_id = rp.paper_id WHERE rp.project_id = ?",
                    (project_id,),
                ).fetchall()
                for paper in papers:
                    text = f"{paper[1] or ''}. {paper[2] or ''}"
                    rows = risk_of_bias.assess(text)
                    risk_of_bias.save(conn, project_id, paper[0], rows)
            rows = risk_of_bias.list_rows(conn, project_id)
            by_paper = {}
            for row in rows:
                by_paper.setdefault(row["paper_id"], []).append(row)
            return jsonify(
                {
                    "rows": rows,
                    "overall": {
                        paper: risk_of_bias.overall(items)
                        for paper, items in by_paper.items()
                    },
                }
            )
        finally:
            conn.close()

    @bp.route("/<project_id>/from-watch", methods=["POST"])
    def from_watch(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            run_id = int(data.get("run_id") or 0)
            if not run_id:
                return jsonify({"error": "run_id required"}), 400
            added = systematic.add_from_watch(conn, project_id, run_id)
            return jsonify({"added": added})
        finally:
            conn.close()

    @bp.route("/<project_id>/brief", methods=["GET"])
    def review_brief(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            text = brief_mod.build_brief(conn, project_id)
            return Response(text, mimetype="text/markdown; charset=utf-8")
        finally:
            conn.close()

    @bp.route("/<project_id>/report.html", methods=["GET"])
    def review_report(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            return Response(
                report_mod.render_html(conn, project_id),
                mimetype="text/html; charset=utf-8",
            )
        finally:
            conn.close()

    @bp.route("/<project_id>/report.pdf", methods=["GET"])
    def review_report_pdf(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            pdf = pdf_report.render_pdf(conn, project_id)
            return Response(
                pdf,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}.pdf"
                },
            )
        finally:
            conn.close()

    @bp.route("/<project_id>/conflicts", methods=["GET"])
    def screening_conflicts(project_id: str):
        conn = _conn()
        try:
            return jsonify({"conflicts": systematic.conflicts(conn, project_id)})
        finally:
            conn.close()

    @bp.route("/<project_id>/adjudicate", methods=["POST"])
    def adjudicate(project_id: str):
        conn = _conn()
        try:
            data = request.get_json(silent=True) or {}
            if not data.get("paper_id") or not data.get("decision"):
                return jsonify({"error": "paper_id and decision required"}), 400
            systematic.adjudicate(
                conn,
                project_id,
                data["paper_id"],
                data["decision"],
                data.get("reason", ""),
                data.get("editor", ""),
            )
            return jsonify(
                {
                    "prisma": systematic.prisma(conn, project_id),
                    "conflicts": systematic.conflicts(conn, project_id),
                }
            )
        finally:
            conn.close()

    @bp.route("/<project_id>/members", methods=["GET", "POST"])
    def project_members(project_id: str):
        conn = _conn()
        try:
            row = systematic.get_project(conn, project_id)
            if not row:
                return jsonify({"error": "project not found"}), 404
            if request.method == "GET":
                if not systematic.can_access(conn, project_id, _owner()):
                    return jsonify({"error": "forbidden"}), 403
                return jsonify({"members": systematic.members(conn, project_id)})
            if row.get("owner") != _owner():
                return jsonify({"error": "only owner can add members"}), 403
            data = request.get_json(silent=True) or {}
            member = (data.get("member") or "").strip()
            if not member:
                return jsonify({"error": "member required"}), 400
            systematic.add_member(conn, project_id, member, data.get("role", "reviewer"))
            return jsonify({"members": systematic.members(conn, project_id)})
        finally:
            conn.close()

    @bp.route("/<project_id>/events", methods=["GET"])
    def review_events(project_id: str):
        conn = _conn()
        try:
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            return jsonify({"events": systematic.list_events(conn, project_id)})
        finally:
            conn.close()

    @bp.route("/import", methods=["POST"])
    def import_project():
        conn = _conn()
        try:
            data = request.get_json(silent=True) or {}
            if not data.get("project"):
                return jsonify({"error": "project payload required"}), 400
            result = export_mod.import_project(conn, data, _owner())
            return jsonify(result), 201
        finally:
            conn.close()

    @bp.route("/<project_id>/export.json", methods=["GET"])
    def export_project(project_id: str):
        conn = _conn()
        try:
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            data = export_mod.export_project(conn, project_id)
            return Response(
                json.dumps(data, ensure_ascii=False, indent=2),
                mimetype="application/json; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}.json"
                },
            )
        finally:
            conn.close()

    return bp