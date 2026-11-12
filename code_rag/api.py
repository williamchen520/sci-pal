"""Independent code-rag HTTP service (P5 UI backend).

Run separately from SciPal:
    python -m code_rag.api --port 5010
"""

from __future__ import annotations

import argparse
import os

import psycopg
from flask import Flask, jsonify, request

from code_rag.service import health
from code_rag.trace import trace


def _search(*args, **kwargs):
    from code_rag.search import search

    return search(*args, **kwargs)


def create_app() -> Flask:
    app = Flask(__name__)

    def _dsn() -> str:
        return os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")

    @app.get("/health")
    def health_route():
        return jsonify(health())

    @app.get("/libraries/<library_id>/status")
    def status(library_id: str):
        try:
            result = health()
            with psycopg.connect(_dsn()) as conn:
                result["library"] = {
                    "library_id": library_id,
                    "snapshots": conn.execute(
                        "SELECT count(*) FROM code_rag.code_snapshots WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                    "units": conn.execute(
                        "SELECT count(*) FROM code_rag.code_units WHERE library_id=%s",
                        (library_id,),
                    ).fetchone()[0],
                }
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.post("/libraries/<library_id>/search")
    def search_route(library_id: str):
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400
        try:
            hits = _search(
                query,
                library_id=library_id,
                top_k=max(1, min(int(body.get("top_k") or 10), 50)),
                snapshot_id=str(body.get("snapshot_id") or ""),
            )
            return jsonify({"query": query, "library_id": library_id, "hits": hits})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    @app.get("/libraries/<library_id>/trace")
    def trace_route(library_id: str):
        unit_id = str(request.args.get("unit_id") or "").strip()
        if not unit_id:
            return jsonify({"error": "unit_id is required"}), 400
        try:
            result = trace(
                unit_id=unit_id,
                library_id=library_id,
                direction=str(request.args.get("direction") or "both"),
                max_hops=int(request.args.get("max_hops") or 2),
                max_nodes=int(request.args.get("max_nodes") or 30),
            )
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 503

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5010)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
