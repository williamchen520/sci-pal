"""Evidence bundle / context drill-down / answer verification routes.

These are the DSH-facing primitives: retrieval returns a structured bundle
(never bare sentences), the agent can drill into a sentence's parent context,
and its answer must pass a deterministic verifier before it becomes formal.
"""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.qa.verify import verify_answer
from services.search.context_expander import ContextExpander


def _fts_bundle(query: str, top_k: int) -> dict:
    """Last-resort evidence bundle using FTS paragraphs, no vector table."""
    from services.search.hybrid_search import get_shared_hybrid
    from services.db.pg_pool import main_read_connection

    hits = get_shared_hybrid().fts_search(query, top_k=top_k)
    if not hits:
        raise RuntimeError("no FTS evidence")
    evidence = []
    pg = main_read_connection()
    try:
        for hit in hits:
            para_id = hit.get("para_id")
            paper_id = hit.get("paper_id")
            if not para_id or not paper_id:
                continue
            rows = pg.execute(
                "SELECT sentence_id, text FROM sentences "
                "WHERE para_id = %s ORDER BY sequence LIMIT 3",
                (para_id,),
            ).fetchall()
            if not rows:
                continue
            evidence.append(
                {
                    "paper_id": paper_id,
                    "para_id": para_id,
                    "section_path": [],
                    "text": hit.get("text") or "",
                    "highlight": [{"sentence_id": rows[0]["sentence_id"], "text": rows[0]["text"]}],
                    "matched_sentences": [
                        {"sentence_id": row["sentence_id"], "text": row["text"]} for row in rows
                    ],
                    "paragraph_details": [
                        {
                            "para_id": para_id,
                            "sentence_ids": [row["sentence_id"] for row in rows],
                            "text": hit.get("text") or "",
                        }
                    ],
                }
            )
    finally:
        pg.close()
    if not evidence:
        raise RuntimeError("no sentence evidence")
    return {
        "query": query,
        "evidence": evidence,
        "sufficient": True,
        "sufficiency": {"sufficient": True, "reason": "fts_fallback"},
        "summaries": [],
    }


def build_evidence_blueprint(
    *,
    db_path,
    get_retriever: Callable[[], Any],
    log: Any,
    sentence_lookup: Callable[[str, str], Any] | None = None,
    get_fallback_retriever: Callable[[], Any] | None = None,
) -> Blueprint:
    bp = Blueprint("evidence", __name__, url_prefix="/api")
    expander = ContextExpander(db_path)

    def _sentence(paper_id: str, sentence_id: str):
        if sentence_lookup is not None:
            return sentence_lookup(paper_id, sentence_id)
        from services.db.pg_pool import main_read_connection

        pg = main_read_connection()
        try:
            return pg.execute(
                "SELECT sentence_id, para_id, paper_id, text, page, bbox, section_id "
                "FROM sentences WHERE paper_id = %s AND sentence_id = %s",
                (paper_id, sentence_id),
            ).fetchone()
        finally:
            pg.close()

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
            fallback = get_fallback_retriever() if get_fallback_retriever else None
            if fallback is None:
                log.exception("evidence search failed")
                return jsonify({"error": str(exc)[:300]}), 500
            log.warning("evidence backend failed; falling back to unified: %s", exc)
            try:
                bundle = fallback.to_evidence_json(
                    query, paper_id=paper_id, top_paragraphs=top_k
                )
            except Exception as fallback_exc:  # noqa: BLE001
                log.warning("unified fallback failed; trying FTS: %s", fallback_exc)
                try:
                    bundle = _fts_bundle(query, top_k)
                except Exception as fts_exc:  # noqa: BLE001
                    log.exception("evidence FTS fallback failed")
                    return jsonify({"error": str(fts_exc)[:300]}), 503
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
