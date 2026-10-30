"""Watch HTTP API: profiles, discovery, runs, digest, read state."""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request, session

from services.watch import discovery, repo, runner


def build_watch_blueprint(*, db_path, log) -> Blueprint:
    bp = Blueprint("watch", __name__, url_prefix="/api/watch")

    @bp.before_request
    def _set_owner():
        g.owner = session.get("user_id") or "default"

    def _owner() -> str:
        return getattr(g, "owner", "default")

    def _owned_run(conn, run_id: int):
        row = repo.get_run(conn, run_id)
        if row and (row.get("owner") or "default") != _owner():
            return None
        return row

    @bp.route("/profiles", methods=["GET", "POST"])
    def profiles():
        conn = repo.connect(db_path)
        try:
            owner = getattr(g, "owner", "default")
            if request.method == "GET":
                return jsonify({"profiles": repo.list_profiles(conn, owner)})
            data = request.get_json(silent=True) or {}
            if not (data.get("name") or "").strip():
                return jsonify({"error": "name required"}), 400
            data["owner"] = owner
            profile_id = repo.create_profile(conn, data)
            return jsonify({"profile_id": profile_id}), 201
        finally:
            conn.close()

    @bp.route("/profiles/<int:profile_id>", methods=["GET", "PUT", "DELETE"])
    def profile(profile_id: int):
        conn = repo.connect(db_path)
        try:
            owner = getattr(g, "owner", "default")
            row = repo.get_profile(conn, profile_id, owner)
            if not row:
                return jsonify({"error": "profile not found"}), 404
            if request.method == "GET":
                return jsonify(row)
            if request.method == "PUT":
                repo.update_profile(conn, profile_id, request.get_json(silent=True) or {})
                return jsonify(repo.get_profile(conn, profile_id, owner))
            repo.delete_profile(conn, profile_id)
            return jsonify({"ok": True})
        finally:
            conn.close()

    @bp.route("/profiles/<int:profile_id>/journals", methods=["GET", "PUT"])
    def journals(profile_id: int):
        conn = repo.connect(db_path)
        try:
            if not repo.get_profile(conn, profile_id, getattr(g, "owner", "default")):
                return jsonify({"error": "profile not found"}), 404
            if request.method == "GET":
                return jsonify({"journals": repo.list_journals(conn, profile_id)})
            data = request.get_json(silent=True) or {}
            entries = data.get("journals") or []
            for entry in entries:
                entry.setdefault("source", "manual")
            repo.set_journals(conn, profile_id, entries)
            return jsonify({"journals": repo.list_journals(conn, profile_id)})
        finally:
            conn.close()

    @bp.route("/profiles/<int:profile_id>/discover", methods=["POST"])
    def discover(profile_id: int):
        conn = repo.connect(db_path)
        try:
            profile = repo.get_profile(conn, profile_id, getattr(g, "owner", "default"))
            if not profile:
                return jsonify({"error": "profile not found"}), 404
            entries = discovery.discover_journals(conn, profile)
            return jsonify({"journals": entries})
        except Exception as exc:  # noqa: BLE001
            log.exception("watch discover failed")
            return jsonify({"error": str(exc)[:300]}), 502
        finally:
            conn.close()

    @bp.route("/profiles/<int:profile_id>/run", methods=["POST"])
    def run(profile_id: int):
        conn = repo.connect(db_path)
        try:
            if not repo.get_profile(conn, profile_id, getattr(g, "owner", "default")):
                return jsonify({"error": "profile not found"}), 404
        finally:
            conn.close()
        try:
            result = runner.run_profile(db_path, profile_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except Exception as exc:  # noqa: BLE001
            log.exception("watch run failed")
            return jsonify({"error": str(exc)[:300]}), 502
        return jsonify(result)

    @bp.route("/profiles/<int:profile_id>/runs", methods=["GET"])
    def runs(profile_id: int):
        conn = repo.connect(db_path)
        try:
            if not repo.get_profile(conn, profile_id, _owner()):
                return jsonify({"error": "profile not found"}), 404
            return jsonify({"runs": repo.list_runs(conn, profile_id)})
        finally:
            conn.close()

    @bp.route("/runs/<int:run_id>", methods=["GET"])
    def run_detail(run_id: int):
        conn = repo.connect(db_path)
        try:
            row = _owned_run(conn, run_id)
            if not row:
                return jsonify({"error": "run not found"}), 404
            return jsonify({"run": row, "items": repo.list_items(conn, run_id)})
        finally:
            conn.close()

    @bp.route("/runs/<int:run_id>/digest.md", methods=["GET"])
    def digest(run_id: int):
        conn = repo.connect(db_path)
        try:
            row = _owned_run(conn, run_id)
            if not row:
                return jsonify({"error": "run not found"}), 404
            return Response(row.get("digest_md") or "", mimetype="text/markdown")
        finally:
            conn.close()

    @bp.route("/profiles/<int:profile_id>/latest", methods=["GET"])
    def latest_profile(profile_id: int):
        conn = repo.connect(db_path)
        try:
            if not repo.get_profile(conn, profile_id, _owner()):
                return jsonify({"error": "profile not found"}), 404
            runs = repo.list_runs(conn, profile_id, limit=1)
            if not runs:
                return jsonify({"run": None, "items": []})
            latest_run = runs[0]
            return jsonify(
                {"run": latest_run, "items": repo.list_items(conn, latest_run["id"])}
            )
        finally:
            conn.close()

    @bp.route("/runs/<int:run_id>/latest", methods=["GET"])
    def latest(run_id: int):
        conn = repo.connect(db_path)
        try:
            row = _owned_run(conn, run_id)
            if not row:
                return jsonify({"error": "run not found"}), 404
            profile_id = row["profile_id"]
            runs = repo.list_runs(conn, profile_id, limit=1)
            latest_run = runs[0] if runs else None
            items = repo.list_items(conn, latest_run["id"]) if latest_run else []
            return jsonify({"run": latest_run, "items": items})
        finally:
            conn.close()

    @bp.route("/topics", methods=["GET"])
    def topics():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "缺少 q"}), 400
        try:
            return jsonify({"topics": discovery.openalex_topic_search(query)})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)[:200]}), 502

    @bp.route("/items/<int:item_id>/read", methods=["POST"])
    def read_item(item_id: int):
        conn = repo.connect(db_path)
        try:
            row = conn.execute(
                "SELECT owner FROM watch_items WHERE id = ?", (item_id,)
            ).fetchone()
            if not row or (row["owner"] or "default") != _owner():
                return jsonify({"error": "item not found"}), 404
            repo.mark_item_read(conn, item_id)
            return jsonify({"ok": True})
        finally:
            conn.close()

    @bp.route("/items/<int:item_id>/feedback", methods=["POST"])
    def feedback(item_id: int):
        conn = repo.connect(db_path)
        try:
            row = conn.execute(
                "SELECT owner FROM watch_items WHERE id = ?", (item_id,)
            ).fetchone()
            if not row or (row["owner"] or "default") != _owner():
                return jsonify({"error": "item not found"}), 404
            data = request.get_json(silent=True) or {}
            value = str(data.get("feedback") or "").strip()
            if value not in {"useful", "not_useful"}:
                return jsonify({"error": "feedback must be useful or not_useful"}), 400
            repo.set_item_feedback(conn, item_id, value)
            return jsonify({"ok": True, "feedback": value})
        finally:
            conn.close()

    @bp.route("/runs/<int:run_id>/read-all", methods=["POST"])
    def read_all(run_id: int):
        conn = repo.connect(db_path)
        try:
            if not _owned_run(conn, run_id):
                return jsonify({"error": "run not found"}), 404
            for item in repo.list_items(conn, run_id):
                repo.mark_item_read(conn, item["id"])
            return jsonify({"ok": True})
        finally:
            conn.close()

    return bp
