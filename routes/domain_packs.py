"""Domain pack HTTP API: list, detail, validation."""

from __future__ import annotations

from flask import Blueprint, jsonify

from services.domain_packs import get_pack, list_packs, validate_pack


def build_domain_packs_blueprint(*, log=None) -> Blueprint:
    bp = Blueprint("domain_packs", __name__, url_prefix="/api/domain-packs")

    @bp.get("")
    @bp.get("/")
    def packs():
        return jsonify({"packs": [pack.summary() for pack in list_packs()]})

    @bp.get("/<pack_id>")
    def detail(pack_id: str):
        pack = get_pack(pack_id)
        if not pack:
            return jsonify({"error": "pack not found"}), 404
        return jsonify(
            {
                **pack.summary(),
                "manifest": pack.manifest,
                "taxonomy": pack.taxonomy,
                "section_types": pack.section_types,
                "evidence_schema": pack.evidence_schema,
                "sources": pack.sources,
                "prompts": pack.prompts,
            }
        )

    @bp.get("/<pack_id>/validate")
    def validate(pack_id: str):
        pack = get_pack(pack_id)
        if not pack:
            return jsonify({"error": "pack not found"}), 404
        return jsonify(validate_pack(pack.path))

    return bp
