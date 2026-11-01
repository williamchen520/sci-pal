"""Paper read-only routes (list / detail / citation neighbourhood).

Pure relocation from ``api_server.py``: response shapes are unchanged so the
frontend keeps working while the router is being split. Contract migration for
these routes happens separately, together with their consumers.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.db.read_router import ReadRouter
from services.tenancy.web import ensure_workspace_scoping, resolve_workspace


def build_papers_blueprint(
    *,
    db_path: Path,
    get_graph: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("papers", __name__, url_prefix="/api")

    def _log(message: str) -> None:
        if callable(log):
            log(message)
        else:
            warning = getattr(log, "warning", None)
            if warning:
                warning(message)

    router = ReadRouter(
        db_path,
        pg_dsn=os.environ.get("SCIPAL_PG_DSN", ""),
        canary_percent=int(os.environ.get("SCIPAL_READ_CANARY_PERCENT", "0") or 0),
    )
    detail_router = ReadRouter(
        db_path,
        pg_dsn=os.environ.get("SCIPAL_PG_DSN", ""),
        canary_percent=int(os.environ.get("SCIPAL_READ_DETAIL_PERCENT", "0") or 0),
    )

    @bp.get("/papers")
    def list_papers():
        workspace_id = resolve_workspace(db_path=db_path)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        canary_key = (
            request.headers.get("X-Request-ID")
            or request.args.get("canary_key")
            or secrets.token_hex(8)
        )
        if router.should_use_pg(canary_key):
            result = router.list_papers(workspace_id, canary_key=canary_key)
            if result.backend == "postgres":
                response = jsonify(
                    {"count": len(result.rows), "papers": result.rows}
                )
                response.headers["X-SciPal-Read-Backend"] = "postgres"
                return response
            _log(f"read canary fell back to SQLite: {result.error}")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            ensure_workspace_scoping(conn)
            rows = conn.execute(
                """
                SELECT paper_id, title, authors, journal, year, doi,
                       total_paragraphs, total_figures, total_tables, workspace_id
                FROM papers WHERE workspace_id = ? ORDER BY year DESC, title
                """,
                (workspace_id,),
            ).fetchall()
        finally:
            conn.close()
        response = jsonify({"count": len(rows), "papers": [dict(row) for row in rows]})
        response.headers["X-SciPal-Read-Backend"] = "sqlite"
        return response

    @bp.get("/papers/<paper_id>")
    def paper_detail(paper_id):
        workspace_id = resolve_workspace(db_path=db_path)
        if not workspace_id:
            return jsonify({"error": "workspace access denied"}), 401
        canary_key = (
            request.headers.get("X-Request-ID")
            or request.args.get("canary_key")
            or secrets.token_hex(8)
        )
        if detail_router.should_use_pg(canary_key):
            result = detail_router.paper_detail(
                paper_id, workspace_id, canary_key=canary_key
            )
            if result.backend == "postgres" and result.payload:
                response = jsonify(result.payload)
                response.headers["X-SciPal-Read-Backend"] = "postgres"
                return response
            if result.error:
                _log(f"paper detail canary fell back to SQLite: {result.error}")
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            ensure_workspace_scoping(conn)
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ? AND workspace_id = ?",
                (paper_id, workspace_id),
            ).fetchone()
            if not paper:
                return jsonify({"error": "Paper not found"}), 404

            cites = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = ? AND c.relation = 'cites'
                  AND p.workspace_id = ?
                ORDER BY c.confidence DESC
                """,
                (paper_id, workspace_id),
            ).fetchall()
            cited_by = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.source_paper_id
                WHERE c.target_paper_id = ? AND c.relation = 'cites'
                  AND p.workspace_id = ?
                ORDER BY c.confidence DESC
                """,
                (paper_id, workspace_id),
            ).fetchall()
            similar = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = ? AND c.relation = 'similar'
                  AND p.workspace_id = ?
                ORDER BY c.confidence DESC LIMIT 10
                """,
                (paper_id, workspace_id),
            ).fetchall()
        finally:
            conn.close()

        response = jsonify(
            {
                "paper": dict(paper),
                "cites": [dict(row) for row in cites],
                "cited_by": [dict(row) for row in cited_by],
                "similar": [dict(row) for row in similar],
            }
        )
        response.headers["X-SciPal-Read-Backend"] = "sqlite"
        return response

    @bp.get("/papers/<paper_id>/graph")
    def paper_graph(paper_id):
        relation = request.args.get("relation", "all")
        direction = request.args.get("direction", "both")
        max_hops = min(_int_arg("max_hops", 1), 3)
        max_total = _int_arg("max_total", 10)

        try:
            graph = get_graph()
            if max_hops <= 1:
                neighbors = graph.get_neighbors(
                    [paper_id], relation=relation, direction=direction
                )[:max_total]
            else:
                neighbors = graph.traverse(
                    [paper_id], max_hops=max_hops, max_total=max_total, relation=relation
                )
        except Exception as exc:
            log.exception("paper_graph failed")
            return jsonify({"error": f"Graph traversal failed: {exc}"}), 500

        return jsonify(
            {
                "paper_id": paper_id,
                "relation": relation,
                "max_hops": max_hops,
                "count": len(neighbors),
                "neighbors": neighbors,
            }
        )

    return bp


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
