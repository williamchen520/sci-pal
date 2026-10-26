"""Reference interchange routes (RIS / EndNote XML import, library listing)."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from services.references.interchange import (
    detect_format,
    parse_endnote_xml,
    parse_ris,
)


def build_references_blueprint(
    *,
    get_library: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("references", __name__, url_prefix="/api")

    @bp.post("/references/import")
    def import_references():
        content = ""
        fmt = "auto"
        if request.files:
            upload = next(iter(request.files.values()))
            content = upload.read().decode("utf-8", errors="replace")
            fmt = request.form.get("format", "auto")
        else:
            body = request.get_json(silent=True) or {}
            content = str(body.get("content") or "")
            fmt = str(body.get("format") or "auto")

        if not content.strip():
            return jsonify({"ok": False, "error": "content is empty"}), 400
        if len(content) > 5_000_000:
            return jsonify({"ok": False, "error": "content too large"}), 400

        chosen = detect_format(content) if fmt in {"auto", ""} else fmt
        if chosen == "ris":
            references = parse_ris(content)
        elif chosen == "endnote_xml":
            references = parse_endnote_xml(content)
        else:
            return jsonify(
                {"ok": False, "error": "unsupported format", "detected": chosen}
            ), 400
        if not references:
            return jsonify({"ok": False, "error": "no records parsed", "format": chosen}), 400

        result = get_library().import_references(references, source=chosen)
        return jsonify({"ok": True, "format": chosen, "parsed": len(references), **result})

    @bp.get("/references")
    def list_references():
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 500))
        except (TypeError, ValueError):
            limit = 50
        library = get_library()
        return jsonify({"ok": True, "count": library.count(), "references": library.list(limit)})

    return bp
