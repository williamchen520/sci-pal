"""Paper read-only routes (list / detail / citation neighbourhood).

Pure relocation from ``api_server.py``: response shapes are unchanged so the
frontend keeps working while the router is being split. Contract migration for
these routes happens separately, together with their consumers.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.db.fallback_stats import record as record_fallback
from services.db.read_router import ReadRouter
from services.tenancy.web import resolve_workspace


def build_papers_blueprint(
    *,
    db_path: Path,
    get_graph: Callable[[], Any],
    log: Any,
    router_factory: Callable[..., Any] = ReadRouter,
    detail_router_factory: Callable[..., Any] = ReadRouter,
) -> Blueprint:
    bp = Blueprint("papers", __name__, url_prefix="/api")

    def _log(message: str) -> None:
        if callable(log):
            log(message)
        else:
            warning = getattr(log, "warning", None)
            if warning:
                warning(message)

    router = router_factory(
        db_path,
        pg_dsn=os.environ.get("SCIPAL_PG_DSN", ""),
        canary_percent=int(os.environ.get("SCIPAL_READ_CANARY_PERCENT", "0") or 0),
    )
    detail_router = detail_router_factory(
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
        result = router.list_papers(workspace_id, canary_key=canary_key)
        if result.backend != "postgres" or result.error:
            _log(f"papers list PG read failed: {result.error}")
            return jsonify({"error": "paper read backend unavailable"}), 503
        response = jsonify({"count": len(result.rows), "papers": result.rows})
        response.headers["X-SciPal-Read-Backend"] = "postgres"
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
        result = detail_router.paper_detail(paper_id, workspace_id, canary_key=canary_key)
        if result.backend != "postgres" or result.error:
            _log(f"paper detail PG read failed: {result.error}")
            return jsonify({"error": "paper read backend unavailable"}), 503
        if not result.payload:
            return jsonify({"error": "Paper not found"}), 404
        response = jsonify(result.payload)
        response.headers["X-SciPal-Read-Backend"] = "postgres"
        return response

    @bp.get("/papers/<paper_id>/graph")
    def paper_graph(paper_id):
        relation = request.args.get("relation", "all")
        direction = request.args.get("direction", "both")
        max_hops = min(_int_arg("max_hops", 1), 3)
        max_total = _int_arg("max_total", 10)
        canary_key = (
            request.headers.get("X-Request-ID")
            or request.args.get("canary_key")
            or secrets.token_hex(8)
        )
        percent = max(0, min(100, int(os.environ.get("SCIPAL_READ_GRAPH_PERCENT", "0") or 0)))
        use_pg = percent >= 100 or (
            percent > 0
            and int(hashlib.sha256(f"graph:{canary_key}".encode()).hexdigest()[:8], 16) % 100
            < percent
        )
        backend = "sqlite"
        try:
            if use_pg:
                from services.search.graph_traverser_pg import PGGraphTraverser

                graph = PGGraphTraverser()
                backend = "postgres"
            else:
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
            if use_pg:
                record_fallback("papers_graph")
                _log(f"paper graph canary fell back to SQLite: {exc}")
                graph = get_graph()
                backend = "sqlite"
                try:
                    if max_hops <= 1:
                        neighbors = graph.get_neighbors(
                            [paper_id], relation=relation, direction=direction
                        )[:max_total]
                    else:
                        neighbors = graph.traverse(
                            [paper_id], max_hops=max_hops, max_total=max_total, relation=relation
                        )
                except Exception as inner:
                    log.exception("paper_graph failed")
                    return jsonify({"error": f"Graph traversal failed: {inner}"}), 500
            else:
                log.exception("paper_graph failed")
                return jsonify({"error": f"Graph traversal failed: {exc}"}), 500

        response = jsonify(
            {
                "paper_id": paper_id,
                "relation": relation,
                "max_hops": max_hops,
                "count": len(neighbors),
                "neighbors": neighbors,
            }
        )
        response.headers["X-SciPal-Read-Backend"] = backend
        return response

    return bp


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
