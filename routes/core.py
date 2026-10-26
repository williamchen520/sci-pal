"""Core routes: health check and unified retrieval (moved out of api_server.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import Blueprint, jsonify, request


def _parse_filters(source) -> Optional[Dict]:
    """Parse V24.2 metadata filters from request args or JSON body."""
    filters = {}
    section = source.get("section") or source.get("section_l1")
    if section:
        filters["section_l1"] = section
    year_min = source.get("year_min")
    if year_min is not None and str(year_min).strip():
        try:
            filters["year_min"] = int(year_min)
        except (ValueError, TypeError):
            pass
    year_max = source.get("year_max")
    if year_max is not None and str(year_max).strip():
        try:
            filters["year_max"] = int(year_max)
        except (ValueError, TypeError):
            pass
    journal = source.get("journal")
    if journal:
        filters["journal"] = journal
    return filters if filters else None


def build_core_blueprint(*, db_path: Path, get_retriever: Callable[[], Any]) -> Blueprint:
    bp = Blueprint("core", __name__)

    @bp.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "sci-pal",
                "version": "V33.17",
                "db_exists": Path(db_path).exists(),
            }
        )

    @bp.route("/api/retrieve", methods=["GET", "POST"])
    def retrieve():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            q = data.get("q", "").strip()
            top_paragraphs = int(data.get("top_paragraphs", 6))
            top_figures = int(data.get("top_figures", 3))
            paper_id = data.get("paper_id") or None
            filters = _parse_filters(data)
        else:
            q = request.args.get("q", "").strip()
            top_paragraphs = int(request.args.get("top_paragraphs", 6))
            top_figures = int(request.args.get("top_figures", 3))
            paper_id = request.args.get("paper_id") or None
            filters = _parse_filters(request.args)

        if not q:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        try:
            result = get_retriever().retrieve(
                query=q,
                paper_id=paper_id,
                top_paragraphs=top_paragraphs,
                top_figures=top_figures,
                filters=filters,
            )
            return jsonify(result)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"Retrieval failed: {str(exc)}"}), 500

    return bp
