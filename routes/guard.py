"""scipal-guard HTTP routes (entity vocabulary + corpus landing)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from services.quality.abbreviations import lookup_abbreviation

from flask import Blueprint, jsonify, request


def build_guard_blueprint(*, get_guard: Callable[[], Any], log: Any) -> Blueprint:
    bp = Blueprint("guard", __name__, url_prefix="/api/guard")

    @bp.post("/check")
    def check():
        body = request.get_json(silent=True) or {}
        text = str(body.get("text") or "")
        if len(text.strip()) < 20:
            return jsonify({"ok": False, "error": "text too short"}), 400
        if len(text) > 200_000:
            return jsonify({"ok": False, "error": "text too large"}), 400
        try:
            report = get_guard().check(text)
        except Exception as exc:  # noqa: BLE001
            log.exception("guard check failed")
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, **report.summary()})

    @bp.get("/stats")
    def stats():
        lexicon = get_guard().lexicon
        by_type = Counter(entry.type for entry in lexicon.entries)
        by_tier = Counter(entry.tier for entry in lexicon.entries)
        return jsonify(
            {
                "ok": True,
                "entries": len(lexicon.entries),
                "surfaces": len(list(lexicon.match_surfaces())),
                "by_type": dict(by_type),
                "by_tier": dict(by_tier),
            }
        )

    @bp.get("/term/<term>")
    def term(term: str):
        entries = get_guard().lexicon.lookup(term)
        return jsonify(
            {
                "ok": True,
                "term": term,
                "abbreviation": lookup_abbreviation(term),
                "entries": [
                    {
                        "type": entry.type,
                        "id": entry.normalized_id,
                        "canonical": entry.canonical,
                        "aliases": list(entry.aliases),
                        "papers": entry.papers,
                        "tier": entry.tier,
                    }
                    for entry in entries
                ],
            }
        )

    return bp
