"""Systematic review routes: project, screening, PRISMA, evidence table."""

from __future__ import annotations

import json
import threading

from flask import Blueprint, Response, g, jsonify, request

from services.review import brief as brief_mod
from services.review import export as export_mod
from services.review import importers
from services.review import docx_report
from services.review import notifications
from services.review import kappa as kappa_mod
from services.review import pdf_report
from services.review import prisma_svg
from services.review import report as report_mod
from services.review import risk_of_bias
from services.review import pico, pg_pdf, pg_report, pg_systematic, systematic


def _pg_projects() -> bool:
    return True


def build_systematic_review_blueprint(*, db_path, log) -> Blueprint:
    bp = Blueprint("review_projects", __name__, url_prefix="/api/review-projects")

    def _owner() -> str:
        return getattr(g, "owner", "default")

    def _audit(conn, project_id, action, target="", detail=""):
        if _pg_projects():
            pg_systematic.log_event(project_id, _owner(), action, target, detail)
            try:
                threading.Thread(
                    target=notifications.notify,
                    args=(
                        db_path,
                        project_id,
                        action,
                        {"actor": _owner(), "target": target, "detail": detail},
                    ),
                    daemon=True,
                ).start()
            except Exception:
                pass
            return
        systematic.log_event(conn, project_id, _owner(), action, target, detail)
        try:
            threading.Thread(
                target=notifications.notify,
                args=(
                    db_path,
                    project_id,
                    action,
                    {"actor": _owner(), "target": target, "detail": detail},
                ),
                daemon=True,
            ).start()
        except Exception:
            pass

    def _conn():
        return None

    @bp.route("", methods=["GET", "POST"])
    def projects():
        conn = _conn()
        try:
            if request.method == "GET":
                if _pg_projects():
                    return jsonify({"projects": pg_systematic.list_projects(_owner())})
                return jsonify({"projects": systematic.list_projects(conn, _owner())})
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            if not name:
                return jsonify({"error": "name required"}), 400
            project_id = (
                pg_systematic.create_project(
                    name, data.get("field_text", ""), data.get("pico") or {}, owner=_owner()
                )
                if _pg_projects()
                else systematic.create_project(
                    conn, name, data.get("field_text", ""), data.get("pico") or {},
                    owner=_owner(),
                )
            )
            _audit(conn, project_id, "project_created", project_id, name)
            return jsonify({"project_id": project_id}), 201
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>", methods=["GET"])
    def project(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not allowed:
                return jsonify({"error": "project not found"}), 404
            return jsonify(row)
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/papers", methods=["POST"])
    def papers(project_id: str):
        conn = _conn()
        try:
            project_row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not allowed:
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            paper_ids = data.get("paper_ids") or []
            if _pg_projects():
                pg_systematic.add_papers(project_id, paper_ids)
            else:
                systematic.add_papers(conn, project_id, paper_ids)
            _audit(conn, project_id, "papers_added", "", str(len(paper_ids)))
            return jsonify({"added": len(paper_ids)})
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/screen", methods=["POST"])
    def screen(project_id: str):
        conn = _conn()
        try:
            data = request.get_json(silent=True) or {}
            if not data.get("paper_id") or not data.get("decision"):
                return jsonify({"error": "paper_id and decision required"}), 400
            if _pg_projects():
                pg_systematic.screen(
                    project_id,
                    data["paper_id"],
                    data["decision"],
                    data.get("reason", ""),
                    data.get("reviewer", ""),
                    data.get("stage", "title_abstract"),
                )
            else:
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
            return jsonify(
                pg_systematic.prisma(project_id)
                if _pg_projects()
                else systematic.prisma(conn, project_id)
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/prisma", methods=["GET"])
    def prisma(project_id: str):
        conn = _conn()
        try:
            return jsonify(
                pg_systematic.prisma(project_id)
                if _pg_projects()
                else systematic.prisma(conn, project_id)
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/evidence", methods=["GET", "POST"])
    def evidence(project_id: str):
        conn = _conn()
        try:
            if request.method == "GET":
                return jsonify(
                    {"rows": pg_systematic.list_evidence(project_id)}
                    if _pg_projects()
                    else {"rows": systematic.list_evidence(conn, project_id)}
                )
            if _pg_projects():
                project_row = pg_systematic.get_project(project_id)
                if not project_row or not pg_systematic.can_access(project_id, _owner()):
                    return jsonify({"error": "project not found"}), 404
                papers = pg_systematic.project_papers(project_id)
                added = 0
                for paper in papers:
                    row = systematic.extract_evidence(paper, project_row.get("pico"))
                    pg_systematic.add_evidence(project_id, paper["paper_id"], row)
                    added += 1
                _audit(conn, project_id, "evidence_extracted", "", str(added))
                return jsonify({"added": added, "rows": pg_systematic.list_evidence(project_id)})
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
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/evidence.csv", methods=["GET"])
    def evidence_csv(project_id: str):
        conn = _conn()
        try:
            return Response(
                pg_systematic.evidence_csv(project_id)
                if _pg_projects()
                else systematic.evidence_csv(conn, project_id),
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}_evidence.csv"
                },
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/pico", methods=["POST"])
    def extract_pico(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not row or not allowed:
                return jsonify({"error": "project not found"}), 404
            result = pico.auto_pico_pg(project_id)
            _audit(conn, project_id, "pico_extracted")
            return jsonify(result)
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/kappa", methods=["GET"])
    def screening_kappa(project_id: str):
        conn = _conn()
        try:
            return jsonify(kappa_mod.kappa_pg(project_id) if _pg_projects() else kappa_mod.kappa(conn, project_id))
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/prisma.svg", methods=["GET"])
    def prisma_diagram(project_id: str):
        conn = _conn()
        try:
            row = pg_systematic.get_project(project_id) if _pg_projects() else systematic.get_project(conn, project_id)
            if not row:
                return jsonify({"error": "project not found"}), 404
            counts = pg_systematic.prisma(project_id) if _pg_projects() else systematic.prisma(conn, project_id)
            svg = prisma_svg.render(row.get("name") or project_id, counts)
            return Response(svg, mimetype="image/svg+xml")
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/risk-of-bias", methods=["GET", "POST"])
    def rob(project_id: str):
        conn = _conn()
        try:
            if _pg_projects():
                if request.method == "POST":
                    return jsonify({"error": "FEATURE_OFFLINE_PG_ONLY"}), 410
                rows = risk_of_bias.list_rows_pg(project_id)
                by_paper = {}
                for row in rows:
                    by_paper.setdefault(row["paper_id"], []).append(row)
                return jsonify({"rows": rows, "overall": {paper: risk_of_bias.overall(items) for paper, items in by_paper.items()}})
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
                _audit(conn, project_id, "risk_of_bias", "", str(len(papers)))
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
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/from-watch", methods=["POST"])
    def from_watch(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not row or not allowed:
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            run_id = int(data.get("run_id") or 0)
            if not run_id:
                return jsonify({"error": "run_id required"}), 400
            added = pg_systematic.add_from_watch(project_id, run_id)
            _audit(conn, project_id, "watch_imported", str(run_id), str(added))
            return jsonify({"added": added})
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/brief", methods=["GET"])
    def review_brief(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not row or not allowed:
                return jsonify({"error": "project not found"}), 404
            text = (
                pg_report.build_brief(project_id)
                if _pg_projects()
                else brief_mod.build_brief(conn, project_id)
            )
            return Response(text, mimetype="text/markdown; charset=utf-8")
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/report.html", methods=["GET"])
    def review_report(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not row or not allowed:
                return jsonify({"error": "project not found"}), 404
            html_body = (
                pg_report.render_html(project_id)
                if _pg_projects()
                else report_mod.render_html(conn, project_id)
            )
            return Response(
                html_body,
                mimetype="text/html; charset=utf-8",
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/report.pdf", methods=["GET"])
    def review_report_pdf(project_id: str):
        conn = _conn()
        try:
            row = (
                pg_systematic.get_project(project_id)
                if _pg_projects()
                else systematic.get_project(conn, project_id)
            )
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not row or not allowed:
                return jsonify({"error": "project not found"}), 404
            pdf = (
                pg_pdf.render_pdf(project_id)
                if _pg_projects()
                else pdf_report.render_pdf(conn, project_id)
            )
            return Response(
                pdf,
                mimetype="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}.pdf"
                },
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/conflicts", methods=["GET"])
    def screening_conflicts(project_id: str):
        conn = _conn()
        try:
            return jsonify({"conflicts": pg_systematic.conflicts(project_id) if _pg_projects() else systematic.conflicts(conn, project_id)})
        finally:
            if conn is not None:
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
            _audit(conn, project_id, "adjudicated", data["paper_id"], data["decision"])
            return jsonify(
                {
                    "prisma": systematic.prisma(conn, project_id),
                    "conflicts": systematic.conflicts(conn, project_id),
                }
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/members", methods=["GET", "POST"])
    def project_members(project_id: str):
        conn = _conn()
        try:
            row = pg_systematic.get_project(project_id) if _pg_projects() else systematic.get_project(conn, project_id)
            if not row:
                return jsonify({"error": "project not found"}), 404
            if request.method == "GET":
                allowed = pg_systematic.can_access(project_id, _owner()) if _pg_projects() else systematic.can_access(conn, project_id, _owner())
                if not allowed:
                    return jsonify({"error": "forbidden"}), 403
                members = pg_systematic.members(project_id) if _pg_projects() else systematic.members(conn, project_id)
                return jsonify({"members": members})
            if row.get("owner") != _owner():
                return jsonify({"error": "only owner can add members"}), 403
            data = request.get_json(silent=True) or {}
            member = (data.get("member") or "").strip()
            if not member:
                return jsonify({"error": "member required"}), 400
            systematic.add_member(conn, project_id, member, data.get("role", "reviewer"))
            _audit(conn, project_id, "member_added", member, data.get("role", "reviewer"))
            return jsonify({"members": systematic.members(conn, project_id)})
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/events", methods=["GET"])
    def review_events(project_id: str):
        conn = _conn()
        try:
            allowed = pg_systematic.can_access(project_id, _owner()) if _pg_projects() else systematic.can_access(conn, project_id, _owner())
            if not allowed:
                return jsonify({"error": "project not found"}), 404
            return jsonify(
                {"events": pg_systematic.list_events(project_id)}
                if _pg_projects()
                else {"events": systematic.list_events(conn, project_id)}
            )
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/import", methods=["POST"])
    def import_project():
        conn = _conn()
        try:
            data = request.get_json(silent=True) or {}
            if not data.get("project"):
                return jsonify({"error": "project payload required"}), 400
            result = export_mod.import_project(conn, data, _owner())
            systematic.log_event(
                conn, result["project_id"], _owner(), "project_imported", "", ""
            )
            return jsonify(result), 201
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/export.json", methods=["GET"])
    def export_project(project_id: str):
        conn = _conn()
        try:
            if _pg_projects():
                if not pg_systematic.can_access(project_id, _owner()):
                    return jsonify({"error": "project not found"}), 404
                data = export_mod.export_project_pg(project_id)
            else:
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
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/import-records", methods=["POST"])
    def import_records(project_id: str):
        conn = _conn()
        try:
            if not pg_systematic.can_access(project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            data = request.get_json(silent=True) or {}
            records = data.get("records") or []
            result = pg_systematic.import_records(project_id, records)
            _audit(
                conn,
                project_id,
                "records_imported",
                "",
                f"matched={result['matched']} unmatched={result['unmatched']}",
            )
            return jsonify(result)
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/import-file", methods=["POST"])
    def import_file(project_id: str):
        conn = _conn()
        try:
            if not pg_systematic.can_access(project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            upload = request.files.get("file")
            if not upload:
                return jsonify({"error": "file required"}), 400
            raw = upload.read()
            if len(raw) > 5 * 1024 * 1024:
                return jsonify({"error": "file too large (max 5MB)"}), 400
            text = raw.decode("utf-8-sig", errors="ignore")
            records = importers.parse_file(upload.filename or "", text)
            if not records:
                return jsonify({"error": "no records parsed (.bib/.csv)"}), 400
            result = pg_systematic.import_records(project_id, records)
            result["parsed"] = len(records)
            _audit(
                conn,
                project_id,
                "file_imported",
                upload.filename or "",
                f"parsed={len(records)} matched={result['matched']}",
            )
            return jsonify(result)
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/webhooks", methods=["GET", "POST"])
    def webhooks(project_id: str):
        if _pg_projects():
            if not pg_systematic.can_access(project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            if request.method == "GET":
                return jsonify({"webhooks": notifications.list_webhooks(None, project_id)})
            data = request.get_json(silent=True) or {}
            url = (data.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return jsonify({"error": "http(s) url required"}), 400
            webhook_id = notifications.add_webhook(
                None, project_id, url, data.get("events", "*"), data.get("secret", "")
            )
            return jsonify({"id": webhook_id}), 201
        conn = _conn()
        try:
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            if request.method == "GET":
                return jsonify({"webhooks": notifications.list_webhooks(conn, project_id)})
            data = request.get_json(silent=True) or {}
            url = (data.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                return jsonify({"error": "http(s) url required"}), 400
            webhook_id = notifications.add_webhook(
                conn, project_id, url, data.get("events", "*"), data.get("secret", "")
            )
            return jsonify({"id": webhook_id}), 201
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/webhooks/<int:webhook_id>", methods=["DELETE"])
    def delete_webhook(project_id: str, webhook_id: int):
        if _pg_projects():
            if not pg_systematic.can_access(project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            notifications.delete_webhook(None, project_id, webhook_id)
            return jsonify({"deleted": webhook_id})
        conn = _conn()
        try:
            if not systematic.can_access(conn, project_id, _owner()):
                return jsonify({"error": "project not found"}), 404
            notifications.delete_webhook(conn, project_id, webhook_id)
            return jsonify({"deleted": webhook_id})
        finally:
            if conn is not None:
                conn.close()

    @bp.route("/<project_id>/report.docx", methods=["GET"])
    def review_report_docx(project_id: str):
        conn = _conn()
        try:
            allowed = (
                pg_systematic.can_access(project_id, _owner())
                if _pg_projects()
                else systematic.can_access(conn, project_id, _owner())
            )
            if not allowed:
                return jsonify({"error": "project not found"}), 404
            payload = (
                pg_pdf.render_docx(project_id)
                if _pg_projects()
                else docx_report.render_docx(conn, project_id)
            )
            return Response(
                payload,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f"attachment; filename={project_id}.docx"
                },
            )
        finally:
            if conn is not None:
                conn.close()

    return bp
