"""Evidence bundle / context drill-down / answer verification routes.

These are the DSH-facing primitives: retrieval returns a structured bundle
(never bare sentences), the agent can drill into a sentence's parent context,
and its answer must pass a deterministic verifier before it becomes formal.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.qa.verify import verify_answer
from services.search.context_expander import ContextExpander


def build_evidence_blueprint(
    *,
    db_path,
    get_retriever: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("evidence", __name__, url_prefix="/api")
    expander = ContextExpander(db_path)

    def _sentence(paper_id: str, sentence_id: str):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT sentence_id, para_id, paper_id, text, page, bbox, section_id "
                "FROM sentences WHERE paper_id = ? AND sentence_id = ?",
                (paper_id, sentence_id),
            ).fetchone()
        finally:
            conn.close()

    @bp.route("/evidence/search", methods=["GET", "POST"])
    def evidence_search():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
        else:
            data = request.args
        query = (data.get("query") or data.get("q") or "").strip()
        if not query:
            return jsonify({"error": "缺少 query"}), 400
        paper_id = (data.get("paper_id") or "").strip() or None
        top_k = int(data.get("top_k") or data.get("top_paragraphs") or 10)
        top_k = min(max(top_k, 1), 50)
        try:
            retriever = get_retriever()
            bundle = retriever.to_evidence_json(
                query, paper_id=paper_id, top_paragraphs=top_k
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("evidence search failed")
            return jsonify({"error": str(exc)[:300]}), 500
        return jsonify(bundle)

    @bp.route("/evidence/context", methods=["GET"])
    def evidence_context():
        paper_id = request.args.get("paper_id", "").strip()
        sentence_id = request.args.get("sentence_id", "").strip()
        para_id = request.args.get("para_id", "").strip()
        before = int(request.args.get("before", 1))
        after = int(request.args.get("after", 1))
        query = request.args.get("query", "").strip()

        sentence = None
        if sentence_id:
            if not paper_id:
                return jsonify({"error": "sentence_id 需要同时提供 paper_id"}), 400
            sentence = _sentence(paper_id, sentence_id)
            if not sentence:
                return jsonify({"error": "sentence not found"}), 404
            para_id = sentence["para_id"]
            query = query or sentence["text"][:300]
        if not para_id:
            return jsonify({"error": "需要 para_id 或 sentence_id"}), 400

        units = expander.expand(
            [{"para_id": para_id, "score": 1.0}],
            mode="window",
            max_parents=1,
            window_before=before,
            window_after=after,
            query=query or None,
        )
        if not units:
            return jsonify({"error": "paragraph not found"}), 404
        unit = units[0]
        return jsonify(
            {
                "paper_id": unit["paper_id"],
                "section_path": unit.get("section_path") or [],
                "page": unit.get("page"),
                "sentence": dict(sentence) if sentence else None,
                "text": unit["text"],
                "paragraphs": [p.get("text", "") for p in unit.get("paragraphs") or []],
                "matched_sentences": unit.get("matched_sentences") or [],
            }
        )

    @bp.route("/verify", methods=["POST"])
    def verify():
        data = request.get_json(silent=True) or {}
        answer = data.get("answer", "")
        if not answer.strip():
            return jsonify({"error": "缺少 answer"}), 400
        report = verify_answer(
            answer,
            evidence_ids=data.get("evidence_ids") or [],
            evidence=data.get("evidence") or None,
        )
        return jsonify(report)

    return bp
