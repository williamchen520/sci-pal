"""System read-only routes: graph statistics and paper communities.

Moved out of ``api_server.py`` as the first slice of the router split. The
dependency-injected factory keeps the module importable in tests.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from contracts import InternalError, NotFound, fail, ok

COMMUNITIES_HINT = (
    "Communities not built yet. Run: python -m build_db.build_communities --apply"
)


def build_system_blueprint(
    *,
    db_path: Path,
    get_graph: Callable[[], Any],
    log: Any,
) -> Blueprint:
    """Build the ``system`` blueprint mounted under ``/api``."""
    bp = Blueprint("system", __name__, url_prefix="/api")

    @bp.get("/graph/stats")
    def graph_stats():
        try:
            return jsonify(ok(get_graph().stats()))
        except Exception:
            log.exception("graph_stats failed")
            error = InternalError("Graph stats failed")
            return jsonify(fail(error)), error.status

    @bp.get("/communities")
    def list_communities():
        min_size = _int_arg("min_size", 1)
        detailed = request.args.get("detailed", "0") == "1"

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            try:
                comms = conn.execute(
                    """
                    SELECT c.community_id, c.size, c.representative_paper_id,
                           c.summary, c.keywords, c.avg_year,
                           p.title as rep_title, p.authors as rep_authors,
                           p.journal as rep_journal, p.year as rep_year
                    FROM paper_communities c
                    LEFT JOIN papers p ON c.representative_paper_id = p.paper_id
                    WHERE c.size >= ?
                    ORDER BY c.size DESC
                    """,
                    (min_size,),
                ).fetchall()
            except sqlite3.OperationalError:
                return jsonify(fail(NotFound(COMMUNITIES_HINT))), 404

            result = []
            for row in comms:
                item = {
                    "community_id": row["community_id"],
                    "size": row["size"],
                    "representative": {
                        "paper_id": row["representative_paper_id"],
                        "title": row["rep_title"],
                        "authors": row["rep_authors"],
                        "journal": row["rep_journal"],
                        "year": row["rep_year"],
                    },
                    "summary": row["summary"],
                    "keywords": row["keywords"],
                    "avg_year": row["avg_year"],
                }
                if detailed:
                    members = conn.execute(
                        """
                        SELECT m.paper_id, m.centrality, p.title, p.year, p.journal
                        FROM community_members m
                        LEFT JOIN papers p ON m.paper_id = p.paper_id
                        WHERE m.community_id = ?
                        ORDER BY m.centrality DESC
                        """,
                        (row["community_id"],),
                    ).fetchall()
                    item["members"] = [dict(member) for member in members]
                result.append(item)
        finally:
            conn.close()

        return jsonify(
            ok(
                {
                    "total_communities": len(result),
                    "total_papers": sum(item["size"] for item in result),
                    "communities": result,
                }
            )
        )

    return bp


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
