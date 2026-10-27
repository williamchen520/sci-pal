"""Local data sandbox routes: profile, aggregate, sample, artifacts, cloud gate."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from services.data_sandbox import audit, policy, store


def build_data_blueprint(*, db_path, log) -> Blueprint:
    bp = Blueprint("data", __name__, url_prefix="/api/data")

    def _owner() -> str:
        return getattr(g, "owner", "default")

    @bp.route("/classify", methods=["GET"])
    def classify():
        path = request.args.get("path", "").strip()
        if not path:
            return jsonify({"error": "缺少 path"}), 400
        data_class = policy.classify(path)
        return jsonify({"data_class": data_class, "policy": policy.session_policy(data_class)})

    @bp.route("/projects", methods=["GET"])
    def projects():
        base = store.root() / store._safe(_owner())
        items = [p.name for p in base.iterdir() if p.is_dir()] if base.exists() else []
        return jsonify({"projects": sorted(items)})

    @bp.route("/profile", methods=["POST"])
    def profile():
        data = request.get_json(silent=True) or {}
        path = data.get("path", "")
        project_id = data.get("project_id", "")
        if not path or not project_id:
            return jsonify({"error": "需要 path 与 project_id"}), 400
        try:
            frame = policy.load_table(path, data.get("sheet"))
            store.create_project(_owner(), project_id, path, frame)
            profile_artifact = store.write_profile(_owner(), project_id, frame)
            sample_artifact = store.write_sample(_owner(), project_id, frame)
            return jsonify(
                {
                    "project_id": project_id,
                    "rows": int(len(frame)),
                    "profile": profile_artifact,
                    "sample": sample_artifact,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("data profile failed")
            return jsonify({"error": str(exc)[:300]}), 500

    @bp.route("/aggregate", methods=["POST"])
    def aggregate():
        data = request.get_json(silent=True) or {}
        path = data.get("path", "")
        project_id = data.get("project_id", "")
        group_by = data.get("group_by") or []
        if not path or not project_id or not group_by:
            return jsonify({"error": "需要 path / project_id / group_by"}), 400
        try:
            frame = policy.load_table(path, data.get("sheet"))
            if not store.load_manifest(_owner(), project_id):
                store.create_project(_owner(), project_id, path, frame)
            artifact = store.write_aggregate(
                _owner(), project_id, frame, group_by, data.get("metrics") or []
            )
            return jsonify({"artifact": artifact})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:300]}), 400

    @bp.route("/sample", methods=["POST"])
    def sample():
        data = request.get_json(silent=True) or {}
        path = data.get("path", "")
        project_id = data.get("project_id", "")
        if not path or not project_id:
            return jsonify({"error": "需要 path 与 project_id"}), 400
        frame = policy.load_table(path, data.get("sheet"))
        if not store.load_manifest(_owner(), project_id):
            store.create_project(_owner(), project_id, path, frame)
        artifact = store.write_sample(_owner(), project_id, frame)
        return jsonify({"artifact": artifact})

    @bp.route("/artifacts", methods=["GET"])
    def artifacts():
        project_id = request.args.get("project_id", "").strip()
        if not project_id:
            return jsonify({"error": "缺少 project_id"}), 400
        return jsonify({"artifacts": store.list_artifacts(_owner(), project_id)})

    @bp.route("/artifacts/<artifact_id>", methods=["GET", "PUT"])
    def artifact(artifact_id: str):
        project_id = request.args.get("project_id") or (request.get_json(silent=True) or {}).get(
            "project_id", ""
        )
        if not project_id:
            return jsonify({"error": "缺少 project_id"}), 400
        try:
            if request.method == "GET":
                return jsonify(store.read_artifact(_owner(), project_id, artifact_id))
            content = (request.get_json(silent=True) or {}).get("content", "")
            return jsonify(
                store.update_artifact(_owner(), project_id, artifact_id, content)
            )
        except KeyError:
            return jsonify({"error": "artifact not found"}), 404

    @bp.route("/artifacts/<artifact_id>/validate", methods=["POST"])
    def validate(artifact_id: str):
        data = request.get_json(silent=True) or {}
        project_id = data.get("project_id", "")
        if not project_id:
            return jsonify({"error": "缺少 project_id"}), 400
        return jsonify(store.validate_artifact(_owner(), project_id, artifact_id))

    @bp.route("/cloud-gate", methods=["POST"])
    def cloud_gate():
        data = request.get_json(silent=True) or {}
        project_id = data.get("project_id", "")
        artifact_id = data.get("artifact_id", "")
        if not project_id or not artifact_id:
            return jsonify({"error": "需要 project_id 与 artifact_id"}), 400
        return jsonify(
            store.cloud_gate(
                _owner(), project_id, artifact_id, data.get("provider", "")
            )
        )

    @bp.route("/cloud-send", methods=["POST"])
    def cloud_send():
        data = request.get_json(silent=True) or {}
        project_id = data.get("project_id", "")
        artifact_id = data.get("artifact_id", "")
        provider = data.get("provider", "unknown")
        if not project_id or not artifact_id:
            return jsonify({"error": "需要 project_id 与 artifact_id"}), 400
        return jsonify(store.log_cloud_send(_owner(), project_id, artifact_id, provider))

    @bp.route("/audit", methods=["GET"])
    def audit_log():
        project_id = request.args.get("project_id") or None
        limit = int(request.args.get("limit", 100))
        return jsonify(
            {"events": audit.list_events(_owner(), project_id, limit=limit)}
        )

    return bp
