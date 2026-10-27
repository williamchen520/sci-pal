"""Online download task routes."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request

_PARSED_PAPER_ORDER = (
    "ORDER BY (total_paragraphs IS NULL) ASC, total_paragraphs DESC"
)


def _find_parsed_paper(filename: str, conn: sqlite3.Connection | None = None):
    """Return the best paper row for a filename (most paragraphs wins)."""
    own_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(str(db_path_for_lookup()))  # type: ignore[name-defined]
        conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT paper_id, filename, title, authors, year, total_paragraphs "
            f"FROM papers WHERE filename = ? {_PARSED_PAPER_ORDER}",
            (filename,),
        ).fetchone()
    finally:
        if own_conn:
            conn.close()


def build_search_downloads_blueprint(
    *,
    db_path: Path,
    project_root: Path,
    get_task_manager: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("search_downloads", __name__)
    globals()["db_path_for_lookup"] = lambda: db_path

    @bp.route("/api/search/download_online", methods=["POST"])
    def download_online_papers():
        """
        V33.2: å¯åŠ¨åœ¨çº¿æ–‡çŒ®ä¸‹è½½ä»»åŠ¡ï¼ˆå¼‚æ­¥ï¼ŒåŽå°æ‰§è¡Œï¼‰ã€‚

        æŽ¥æ”¶ç”¨æˆ·å‹¾é€‰çš„åœ¨çº¿æ–‡çŒ® PMCID åˆ—è¡¨ï¼ŒåŽå°è‡ªåŠ¨ï¼š
          1. ä¸‹è½½ PMC XML å…¨æ–‡ï¼ˆè‡ªåŠ¨è¿‡æ»¤åªæœ‰æ‘˜è¦çš„ï¼‰
          2. å¢žé‡å¯¼å…¥åˆ° research.dbï¼ˆä¸æ¸…ç©ºæ—§æ•°æ®ï¼‰
          3. å¢žé‡å»ºå‘é‡ç´¢å¼•ï¼ˆåªå¯¹æ–°è®ºæ–‡åš embeddingï¼Œè¿½åŠ åˆ° chromaï¼‰

        Request body (JSON):
          pmc_ids: ["PMC1234567", "PMC7654321", ...] ï¼ˆå¿…å¡«ï¼ŒPMCID åˆ—è¡¨ï¼‰

        Returns:
          {
            "task_id": "dl_abc123...",
            "status": "running",
            "total": 10,
            "message": "ä¸‹è½½ä»»åŠ¡å·²å¯åŠ¨ï¼Œç”¨ task_id è½®è¯¢ /api/search/download_status èŽ·å–è¿›åº¦"
          }
        """
        data = request.get_json(silent=True) or {}
        pmc_ids = data.get("pmc_ids", [])

        if not pmc_ids:
            return jsonify({"error": "ç¼ºå°‘ pmc_ids å‚æ•°ï¼ˆPMCID åˆ—è¡¨ï¼‰"}), 400

        # è§„èŒƒåŒ– PMCID æ ¼å¼
        normalized_ids = []
        for pid in pmc_ids:
            pid = str(pid).strip()
            if not pid:
                continue
            if not pid.upper().startswith("PMC"):
                pid = f"PMC{pid}"
            normalized_ids.append(pid.upper())

        if not normalized_ids:
            return jsonify({"error": "pmc_ids åˆ—è¡¨ä¸ºç©º"}), 400

        try:
            from services.search.online_downloader import get_online_downloader
            downloader = get_online_downloader()
            task_id = downloader.start_download(normalized_ids)

            return jsonify({
                "task_id": task_id,
                "status": "running",
                "total": len(normalized_ids),
                "message": "ä¸‹è½½ä»»åŠ¡å·²å¯åŠ¨ï¼Œç”¨ task_id è½®è¯¢ /api/search/download_status èŽ·å–è¿›åº¦",
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"å¯åŠ¨ä¸‹è½½ä»»åŠ¡å¤±è´¥: {str(e)}"}), 500


    # download_status å·²è¿å…¥ routes/search.pyï¼ˆB3cï¼‰


    # ============================================================
    # V33.3: ä¸‹è½½åŽ†å²ã€é˜Ÿåˆ—ç®¡ç†ã€å¤±è´¥é‡è¯• API
    # ============================================================

    # download_history å·²è¿å…¥ routes/search.pyï¼ˆB3cï¼‰


    # download_queue å·²è¿å…¥ routes/search.pyï¼ˆB3cï¼‰


    @bp.route("/api/search/retry_download", methods=["POST"])
    def retry_download():
        """
        V33.3: é‡è¯•ä¸‹è½½å¤±è´¥çš„æ–‡çŒ®ã€‚

        ä¸¤ç§æ¨¡å¼ï¼š
          1. æŒ‡å®š task_idï¼šé‡è¯•è¯¥ä»»åŠ¡ä¸­ä¸‹è½½å¤±è´¥çš„ PMCID
          2. æŒ‡å®š pmc_idsï¼šç›´æŽ¥é‡è¯•æŒ‡å®šçš„ PMCID åˆ—è¡¨

        Request body (JSON):
          task_id: ä»»åŠ¡ IDï¼ˆå¯é€‰ï¼Œä¸Ž pmc_ids äºŒé€‰ä¸€ï¼‰
          pmc_ids: PMCID åˆ—è¡¨ï¼ˆå¯é€‰ï¼Œä¸Ž task_id äºŒé€‰ä¸€ï¼‰

        Returns:
          {
            "task_id": str,
            "retry_count": int,
            "message": str
          }
        """
        data = request.get_json(silent=True) or {}
        task_id = data.get("task_id", "").strip()
        pmc_ids = data.get("pmc_ids", [])

        # å¦‚æžœæŒ‡å®šäº† task_idï¼Œä»Žè¯¥ä»»åŠ¡ä¸­èŽ·å–å¤±è´¥çš„ PMCID
        if task_id:
            try:
                from services.search.online_downloader import get_task_manager
                manager = get_task_manager()
                task = manager.get_task(task_id)
                if task is None:
                    return jsonify({"error": f"ä»»åŠ¡ä¸å­˜åœ¨: {task_id}"}), 404
                pmc_ids = task.failed_pmc_ids or []
                if not pmc_ids:
                    return jsonify({"error": "è¯¥ä»»åŠ¡æ²¡æœ‰å¤±è´¥çš„æ–‡çŒ®"}), 400
            except Exception as e:
                return jsonify({"error": f"èŽ·å–ä»»åŠ¡å¤±è´¥: {str(e)}"}), 500

        if not pmc_ids:
            return jsonify({"error": "ç¼ºå°‘ pmc_ids æˆ– task_id å‚æ•°"}), 400

        # è§„èŒƒåŒ– PMCID
        normalized_ids = []
        for pid in pmc_ids:
            pid = str(pid).strip()
            if not pid:
                continue
            if not pid.upper().startswith("PMC"):
                pid = f"PMC{pid}"
            normalized_ids.append(pid.upper())

        if not normalized_ids:
            return jsonify({"error": "PMCID åˆ—è¡¨ä¸ºç©º"}), 400

        try:
            from services.search.online_downloader import get_online_downloader
            downloader = get_online_downloader()
            new_task_id = downloader.start_download(normalized_ids)

            return jsonify({
                "task_id": new_task_id,
                "retry_count": len(normalized_ids),
                "message": f"å·²å¯åŠ¨é‡è¯•ä»»åŠ¡ï¼Œå…± {len(normalized_ids)} ç¯‡æ–‡çŒ®",
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"å¯åŠ¨é‡è¯•ä»»åŠ¡å¤±è´¥: {str(e)}"}), 500


    @bp.route("/api/search/clear_download_history", methods=["POST"])
    def clear_download_history():
        """
        V33.3: æ¸…ç©ºä¸‹è½½åŽ†å²è®°å½•ï¼ˆåªä¿ç•™æ­£åœ¨è¿è¡Œçš„ï¼‰ã€‚

        Returns:
          { "cleared": int, "message": str }
        """
        try:
            from services.search.online_downloader import get_task_manager
            manager = get_task_manager()
            cleared = manager.clear_history()

            return jsonify({
                "cleared": cleared,
                "message": f"å·²æ¸…ç©º {cleared} æ¡åŽ†å²è®°å½•",
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"æ¸…ç©ºåŽ†å²å¤±è´¥: {str(e)}"}), 500





    return bp

