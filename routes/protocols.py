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
        try:
            offset = max(0, int(request.args.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        query = str(request.args.get("q") or "").strip()
        service = get_service()
        rows = service.list(limit, offset, query)
        total = service.count(query) if hasattr(service, "count") else len(rows)
        return jsonify(
            {"ok": True, "count": len(rows), "total": total, "offset": offset, "protocols": rows}
        )

    @bp.get("/protocols/<protocol_id>")
    def get_protocol(protocol_id: str):
        record = get_service().get(protocol_id)
        if record is None:
            return jsonify({"ok": False, "error": "protocol not found"}), 404
        return jsonify({"ok": True, "protocol": record})

    # ------------------------------------------------------------- runs
    @bp.post("/protocols/<protocol_id>/runs")
    def add_run(protocol_id: str):
        service = get_service()
        if service.get(protocol_id) is None:
            return jsonify({"ok": False, "error": "protocol not found"}), 404
        body = request.get_json(silent=True) or {}
        run = service.add_run(
            protocol_id,
            title=str(body.get("title") or ""),
            operator=str(body.get("operator") or ""),
            run_date=str(body.get("run_date") or ""),
            status=str(body.get("status") or "planned"),
            result=str(body.get("result") or ""),
            notes=str(body.get("notes") or ""),
            done_steps=body.get("done_steps"),
        )
        return jsonify({"ok": True, "run": run})

    @bp.get("/protocols/<protocol_id>/runs")
    def list_runs(protocol_id: str):
        try:
            limit = max(1, min(int(request.args.get("limit", 50)), 200))
        except (TypeError, ValueError):
            limit = 50
        rows = get_service().list_runs(protocol_id, limit)
        return jsonify({"ok": True, "count": len(rows), "runs": rows})

    @bp.get("/experiments")
    def recent_runs():
        try:
            limit = max(1, min(int(request.args.get("limit", 20)), 100))
        except (TypeError, ValueError):
            limit = 20
        rows = get_service().recent_runs(limit)
        return jsonify({"ok": True, "count": len(rows), "runs": rows})

    @bp.patch("/experiments/<run_id>")
    def update_run(run_id: str):
        body = request.get_json(silent=True) or {}
        run = get_service().update_run(run_id, **body)
        if run is None:
            return jsonify({"ok": False, "error": "run not found or no fields"}), 404
        return jsonify({"ok": True, "run": run})

    @bp.delete("/experiments/<run_id>")
    def delete_run(run_id: str):
        if not get_service().delete_run(run_id):
            return jsonify({"ok": False, "error": "run not found"}), 404
        return jsonify({"ok": True})

    @bp.get("/protocols/<protocol_id>/export")
    def export_protocol(protocol_id: str):
        content = get_service().export_markdown(protocol_id)
        if content is None:
            return jsonify({"ok": False, "error": "protocol not found"}), 404
        from flask import Response

        filename = f"protocol_{protocol_id}.md"
        return Response(
            content,
            mimetype="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return bp
