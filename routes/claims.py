"""Claim pilot HTTP API: cards, evidence search, decisions."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from services.claims import service


def build_claims_blueprint(*, db_path, log=None, get_llm=None, get_retriever=None) -> Blueprint:
    bp = Blueprint("claims", __name__, url_prefix="/api/claims")
    service.ensure_schema(db_path)

    @bp.get("")
    @bp.get("/")
    def listing():
        conn = service.connect(db_path)
        try:
            return jsonify({"claims": service.list_claims(conn)})
        finally:
            conn.close()

    @bp.get("/<claim_id>")
    def detail(claim_id: str):
        conn = service.connect(db_path)
        try:
            claim = service.get_claim(conn, claim_id)
            if not claim:
                return jsonify({"error": "claim not found"}), 404
            return jsonify(claim)
        finally:
            conn.close()

    @bp.post("/<claim_id>/search")
    def search(claim_id: str):
        data = request.get_json(silent=True) or {}
        direction = str(data.get("direction") or "support")
        if direction not in {"support", "oppose"}:
            return jsonify({"error": "direction must be support or oppose"}), 400
        conn = service.connect(db_path)
        try:
            return jsonify(
                {"candidates": service.search_candidates(conn, claim_id, direction=direction)}
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        finally:
            conn.close()

    @bp.post("/<claim_id>/interrogate")
    def interrogate(claim_id: str):
        data = request.get_json(silent=True) or {}
        direction = str(data.get("direction") or "support")
        if direction not in {"support", "oppose"}:
            return jsonify({"error": "direction must be support or oppose"}), 400
        use_llm = bool(data.get("use_llm"))
        client = get_llm() if (use_llm and get_llm) else None
        retriever = get_retriever() if get_retriever else None
        conn = service.connect(db_path)
        try:
            candidates = service.interrogate(
                conn,
                claim_id,
                direction=direction,
                use_llm=use_llm,
                llm_client=client,
                retriever=retriever,
                limit=min(int(data.get("limit") or 5), 8),
            )
            return jsonify({"candidates": candidates, "use_llm": use_llm})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        finally:
            conn.close()

    @bp.post("/<claim_id>/evidence")
    def evidence(claim_id: str):
        data = request.get_json(silent=True) or {}
        sentence_id = str(data.get("sentence_id") or "").strip()
        relation = str(data.get("relation") or "supports").strip()
        if not sentence_id:
            return jsonify({"error": "sentence_id required"}), 400
        conn = service.connect(db_path)
        try:
            result = service.add_evidence(
                conn,
                claim_id,
                sentence_id,
                relation,
                rationale=str(data.get("rationale") or ""),
                strength=float(data.get("strength") or 0.5),
            )
            return jsonify(result), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            conn.close()

    @bp.post("/<claim_id>/decision")
    def decision(claim_id: str):
        data = request.get_json(silent=True) or {}
        try:
            claim = service.decide(
                conn := service.connect(db_path),
                claim_id,
                str(data.get("decision") or ""),
                note=str(data.get("note") or ""),
            )
            return jsonify(claim)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @bp.post("/<claim_id>/note")
    def note(claim_id: str):
        data = request.get_json(silent=True) or {}
        text = str(data.get("note") or "").strip()
        if not text:
            return jsonify({"error": "note required"}), 400
        conn = service.connect(db_path)
        try:
            return jsonify(service.add_note(conn, claim_id, text))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        finally:
            conn.close()

    @bp.get("/<claim_id>/events")
    def events(claim_id: str):
        conn = service.connect(db_path)
        try:
            claim = service.get_claim(conn, claim_id)
            if not claim:
                return jsonify({"error": "claim not found"}), 404
            return jsonify({"events": claim.get("events", [])})
        finally:
            conn.close()

    return bp
