"""protocols.io P1 routes: import one protocol, list, detail."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_protocols_blueprint(
    *,
    get_service: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("protocols", __name__, url_prefix="/api")

    @bp.post("/protocols/import")
    def import_protocol():
        body = request.get_json(silent=True) or {}
        payload = body.get("payload")
        try:
            if isinstance(payload, dict):
                result = get_service().import_payload(payload, url=str(body.get("url") or ""))
            else:
                protocol_id = str(body.get("protocol_id") or body.get("id") or "").strip()
                if not protocol_id:
                    return jsonify({"ok": False, "error": "protocol_id required"}), 400
                result = get_service().import_protocol(protocol_id)
        except (RuntimeError, ValueError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            log.exception("protocol import failed")
            return jsonify({"ok": False, "error": str(exc)}), 500
        return jsonify({"ok": True, **result})

    @bp.get("/protocols")
    def list_protocols():
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 200))
        except (TypeError, ValueError):
            limit = 50
        rows = get_service().list(limit)
        return jsonify({"ok": True, "count": len(rows), "protocols": rows})

    @bp.get("/protocols/<protocol_id>")
    def get_protocol(protocol_id: str):
        record = get_service().get(protocol_id)
        if record is None:
            return jsonify({"ok": False, "error": "protocol not found"}), 404
        return jsonify({"ok": True, "protocol": record})

    return bp
