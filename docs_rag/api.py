"""HTTP provider for the independent docs RAG (scipal_docs)."""

from __future__ import annotations

import argparse
import os

import psycopg
from flask import Flask, jsonify, request

from docs_rag.search import search


def _dsn() -> str:
    value = os.environ.get("SCIPAL_DOCS_READ_DSN") or os.environ.get("SCIPAL_DOCS_DSN", "")
    if not value:
        raise RuntimeError("SCIPAL_DOCS_READ_DSN is required")
    return value


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        with psycopg.connect(_dsn(), connect_timeout=5) as conn:
            documents = conn.execute("SELECT count(*) FROM docs_rag.documents").fetchone()[0]
            chunks = conn.execute("SELECT count(*) FROM docs_rag.chunks").fetchone()[0]
        return jsonify({"ok": True, "documents": documents, "chunks": chunks})

    @app.post("/search")
    def search_route():
        body = request.get_json(silent=True) or {}
        query = str(body.get("query") or "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400
        mode = str(body.get("mode") or "hybrid")
        try:
            hits = search(
                query,
                top_k=max(1, min(int(body.get("top_k") or 8), 50)),
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:500]}), 503
        return jsonify({"query": query, "mode": mode, "hits": hits})

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5011)
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
