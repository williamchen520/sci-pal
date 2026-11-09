"""System read-only routes: graph statistics and paper communities.

Moved out of ``api_server.py`` as the first slice of the router split. The
dependency-injected factory keeps the module importable in tests.
"""

from __future__ import annotations

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
        # Communities were never migrated to PostgreSQL; do not fall back to SQLite.
        return jsonify(fail(NotFound(COMMUNITIES_HINT))), 404

    return bp


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
