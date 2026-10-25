"""Paper read-only routes (list / detail / citation neighbourhood).

Pure relocation from ``api_server.py``: response shapes are unchanged so the
frontend keeps working while the router is being split. Contract migration for
these routes happens separately, together with their consumers.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_papers_blueprint(
    *,
    db_path: Path,
    get_graph: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("papers", __name__, url_prefix="/api")

    @bp.get("/papers")
    def list_papers():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT paper_id, title, authors, journal, year, doi,
                       total_paragraphs, total_figures, total_tables
                FROM papers ORDER BY year DESC, title
                """
            ).fetchall()
        finally:
            conn.close()
        return jsonify({"count": len(rows), "papers": [dict(row) for row in rows]})

    @bp.get("/papers/<paper_id>")
    def paper_detail(paper_id):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            paper = conn.execute(
                "SELECT * FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            if not paper:
                return jsonify({"error": "Paper not found"}), 404

            cites = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = ? AND c.relation = 'cites'
                ORDER BY c.confidence DESC
                """,
                (paper_id,),
            ).fetchall()
            cited_by = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.source_paper_id
                WHERE c.target_paper_id = ? AND c.relation = 'cites'
                ORDER BY c.confidence DESC
                """,
                (paper_id,),
            ).fetchall()
            similar = conn.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = ? AND c.relation = 'similar'
                ORDER BY c.confidence DESC LIMIT 10
                """,
                (paper_id,),
            ).fetchall()
        finally:
            conn.close()

        return jsonify(
            {
                "paper": dict(paper),
                "cites": [dict(row) for row in cites],
                "cited_by": [dict(row) for row in cited_by],
                "similar": [dict(row) for row in similar],
            }
        )

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
