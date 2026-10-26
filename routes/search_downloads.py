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


    # ---------------------------------------------------------------------------
    # V33.17-6Bè¡¥ä¸: è§£æž + å†™åº“çš„**å”¯ä¸€å®žçŽ°**ä¸Ž**å”¯ä¸€é‚£æŠŠé”**
    #
    # ä¸ºä»€ä¹ˆæŠ½å‡ºæ¥ï¼š`_parse_lock` åŽŸå…ˆåªæœ‰å¼‚æ­¥è·¯ç”±ä½¿ç”¨ï¼ŒåŒæ­¥è·¯ç”±ï¼ˆå‰ç«¯ã€Œè§£æžã€æŒ‰é’®ï¼‰
    # ç›´æŽ¥è·‘ docling â†’ å‰ç«¯ç‚¹ä¸€æ¬¡ + MCP æäº¤ä¸€æ¬¡ = ä¸¤ä»½ docling å¹¶å‘ï¼Œ
    # æ­£æ˜¯è¿™æŠŠé”çš„æ³¨é‡Šé‡Œæ˜Žç¡®è¦é˜²çš„ã€ŒåŒä»½å†…å­˜ + æŠ¢ CPUã€ã€‚é”å¿…é¡»ä¸‹æ²‰åˆ°å”¯ä¸€å®žçŽ°é‡Œã€‚
    #
    # âš ï¸ ä¸¤ä¸ªè§£æžå…¥å£éƒ½åªè°ƒç”¨ `_parse_and_store()`ï¼Œ**ä¸è®¸**åœ¨å¤–é¢å†
    #    `_parse_lock.acquire()` â€”â€” `threading.Lock` ä¸å¯é‡å…¥ï¼Œä¼šè‡ªé”ã€‚
    #    å¼‚æ­¥è·¯ç”±ä¸ºäº†æ˜¾ç¤ºã€ŒæŽ’é˜Ÿä¸­ã€åªåšä¸€æ¬¡ã€Œéžé˜»å¡žè¯•æŠ¢ + ç«‹åˆ»å½’è¿˜ã€ã€‚
    # ---------------------------------------------------------------------------
    _parse_lock = threading.Lock()

    # T3-3: è§£æžä»»åŠ¡å¹¶å‘ä¸Šé™ã€‚è¶…è¿‡å°±ç›´æŽ¥ 429ï¼Œ**ä¸è®¸é™é»˜æŽ’é˜Ÿ**ã€‚
    # ä¸ºä»€ä¹ˆæ˜¯ 3ï¼šå•å®žä¾‹éƒ¨ç½²ï¼›docling ä¸€æ¬¡åªè·‘ä¸€ä¸ªï¼ˆ`_parse_lock` ä¸²è¡Œï¼‰ï¼Œ
    # å¦å¤–ç»™ã€Œå‰ç«¯ä¸€é”®ã€ä¸Žã€ŒMCP æäº¤ã€å„ç•™ä¸€ä¸ªæŽ’é˜Ÿä½ã€‚å†å¤šåªæ˜¯æŠŠçº¿ç¨‹å †åœ¨é”ä¸Šã€‚
    PARSE_MAX_CONCURRENT = 3

    # å‡†å…¥é”ï¼šä¸Ž `_parse_lock` **åˆ†å¼€**ï¼Œåªä¿æŠ¤ã€ŒæŸ¥ running æ•° + create_taskã€è¿™ä¸€å°æ®µï¼Œ
    # é¿å…å‡†å…¥åˆ¤å®šçš„å¼€é”€è¢«è§£æžä¸²è¡ŒåŒ–ç‰µè¿žï¼ˆå¦åˆ™ç¬¬ 4 ä¸ªè¯·æ±‚è¦ç­‰è§£æžå®Œæ‰æ‹¿åˆ° 429ï¼‰ã€‚
    _parse_admit_lock = threading.Lock()


    def _parse_running_count() -> int:
        """å½“å‰å¤„äºŽ running çš„è§£æžä»»åŠ¡æ•°ï¼ˆå£å¾„ï¼štype='parse_paper' AND status='running'ï¼‰ã€‚

        ä¸å« completed / failed / cancelled â€”â€” é‚£äº›å·²ç»é‡Šæ”¾äº†å¹¶å‘é¢åº¦ã€‚
        """
        import sqlite3

        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE type = 'parse_paper' AND status = 'running'"
            ).fetchone()[0]
        finally:
            conn.close()


    class ParseStoreError(RuntimeError):
        """è§£æžæˆåŠŸã€ä½†å†™åº“å¤±è´¥ï¼ˆä¸Žã€Œè§£æžæœ¬èº«å¤±è´¥ã€åŒºåˆ†ï¼Œä¾¿äºŽè·¯ç”±ç»™å‡ºå‡†ç¡®çš„ errorï¼‰ã€‚"""


    class ParseCancelled(RuntimeError):
        """ä»»åŠ¡å·²å–æ¶ˆï¼Œæœ¬æ¬¡è§£æžæ”¾å¼ƒï¼ˆ**æ•°æ®ä¸è¿›åº“**ï¼‰ã€‚

        T3-1: `stage` æ ‡æ˜Žå–æ¶ˆç”Ÿæ•ˆçš„é˜¶æ®µï¼Œä¾›æ—¥å¿—åŒºåˆ†ï¼š
          Â· `æŽ’é˜ŸæœŸé—´` â€”â€” æ‹¿åˆ°é”åŽå‘çŽ°å·²è¢«å–æ¶ˆï¼Œ**è¿ž docling éƒ½ä¸è·‘**ï¼›
          Â· `è§£æžåŽ`   â€”â€” docling å·²è·‘å®Œï¼Œå†™åº“å‰å‘çŽ°å·²è¢«å–æ¶ˆã€‚
        """

        def __init__(self, message: str, stage: str = "") -> None:
            super().__init__(message)
            self.stage = stage


    def _parse_and_store(
        pdf_path, filename: str, before_store=None, on_acquired=None, on_waiting=None
    ) -> Dict:
        """docling è§£æž + å†™åº“ï¼Œå…¨ç¨‹æŒæœ‰ `_parse_lock`ï¼ˆä¸²è¡ŒåŒ–ï¼‰ã€‚

        Args:
            pdf_path: PDF ç»å¯¹è·¯å¾„
            filename: åŽŸå§‹æ–‡ä»¶åï¼ˆmetadata ç¼º title æ—¶å…œåº•ï¼‰
            before_store: å¯é€‰å›žè°ƒï¼Œåœ¨**è§£æžå®ŒæˆåŽã€å†™åº“ä¹‹å‰**ã€**é”å†…**è°ƒç”¨ã€‚
                è¿”å›ž True è¡¨ç¤ºæ”¾å¼ƒå†™åº“ï¼ˆå¼‚æ­¥è·¯ç”±ç”¨å®ƒåšå–æ¶ˆçš„æœ€åŽä¸€é“é—¸ï¼‰ï¼›
                å›žè°ƒé‡Œå¯ä»¥é¡ºå¸¦æ›´æ–°è¿›åº¦ï¼ˆæ­¤åˆ»ä»»åŠ¡ä»æ˜¯ runningï¼Œå†™å¾—è¿›åŽ»ï¼‰ã€‚
            on_waiting: å¯é€‰å›žè°ƒï¼Œåœ¨**ç¡®è®¤è¦æŽ’é˜Ÿ**ï¼ˆè¯•æŠ¢é”å¤±è´¥ï¼‰æ—¶ã€é˜»å¡žå–é”ä¹‹å‰è°ƒç”¨ã€‚
                å¿…é¡»æ”¾åœ¨**æ¨¡å— import ä¹‹åŽ**ï¼šdocling çš„ import é¦–æ¬¡è¦ 10~15 ç§’ï¼Œ
                æ”¾åœ¨ import ä¹‹å‰è¯•æŠ¢ä¼šæ‘¸åˆ°ä¸€ä¸ªã€Œæš‚æ—¶ç©ºé—²ã€çš„é”ï¼Œä»Žè€Œæ¼æŠ¥æŽ’é˜Ÿï¼ˆT4-2ï¼‰ã€‚
            on_acquired: å¯é€‰å›žè°ƒï¼Œåœ¨ **`_parse_lock` å·²å–å¾—ã€ä½†å°šæœªå¼€å§‹è§£æž** æ—¶è°ƒç”¨
                ï¼ˆ`with` å—å†…ç¬¬ä¸€è¡Œï¼Œæ—©äºŽ `ParserOrchestrator()` æž„é€ ï¼‰ã€‚
                ç”¨é€”ï¼šæŠŠã€ŒæŽ’é˜Ÿä¸­ã€åˆ‡æˆã€Œè§£æžä¸­ã€â€”â€” æŽ’é˜ŸæœŸé—´è¿›åº¦æ–‡æ¡ˆå¿…é¡»åœåœ¨
                ã€ŒæŽ’é˜Ÿä¸­ã€ï¼Œå¦åˆ™æŽ’é˜Ÿå®Œå…¨ä¸å¯è§‚æµ‹ï¼ˆT4-2ï¼‰ã€‚
                å¼‚å¸¸ä¼ æ’­ï¼šå›žè°ƒæŠ›å¼‚å¸¸ = æ”¾å¼ƒæœ¬æ¬¡è§£æžï¼Œé”ç”± `with` è‡ªåŠ¨é‡Šæ”¾ï¼Œ
                å¼‚å¸¸åŽŸæ ·æŠ›ç»™è°ƒç”¨æ–¹ï¼ˆä¸åžã€ä¸è½¬æˆ ParseStoreErrorï¼‰ã€‚

        Returns:
            `{"paper_id", "title", "paragraph_count", "stats"}`

        Raises:
            ParseCancelled: `before_store` è¿”å›ž Trueï¼ˆ**æœªå†™åº“**ï¼‰
            ParseStoreError: `insert_paper` è¿”å›ž False
            ImportError: build_db è§£æžæ¨¡å—ä¸å¯ç”¨ï¼ˆåœ¨å–é”ä¹‹å‰å°±æŠ›ï¼Œä¸ä¼šå¡ä½é˜Ÿåˆ—ï¼‰
            Exception: docling è§£æžæœ¬èº«å¤±è´¥ï¼›æˆ– `on_acquired` / `before_store` æŠ›å‡ºçš„å¼‚å¸¸
        """
        from build_db.parsers.parser_orchestrator import ParserOrchestrator
        from build_db.db_writer import DatabaseWriter

        # T4-2: è¯•æŠ¢ä¸€æ¬¡åˆ¤ã€Œè¦ä¸è¦æŽ’é˜Ÿã€ï¼Œ**å¿…é¡»åœ¨ import ä¹‹åŽ**ã€‚
        # docling çš„ import é¦–æ¬¡è¦ 10~15 ç§’ï¼šè‹¥åœ¨ import å‰è¯•æŠ¢ï¼Œå…ˆåˆ°çš„çº¿ç¨‹è¿˜å¡åœ¨
        # import é‡Œã€é”æ˜¯ç©ºçš„ â†’ åŽåˆ°çš„ä»»åŠ¡ä¼šè¯¯åˆ¤ã€Œä¸ç”¨æŽ’é˜Ÿã€ï¼ŒéšåŽé™é»˜é˜»å¡žåœ¨ with ä¸Šã€‚
        # è¯•æŠ¢æˆåŠŸå¿…é¡»ç«‹åˆ»å½’è¿˜ï¼ˆthreading.Lock ä¸å¯é‡å…¥ï¼‰ï¼ŒçœŸæ­£å–é”äº¤ç»™ä¸‹é¢çš„ withã€‚
        if on_waiting is not None:
            if _parse_lock.acquire(blocking=False):
                _parse_lock.release()
            else:
                on_waiting()

        # åŒæ­¥è·¯ç”±æŽ’é˜Ÿæ˜¯é¢„æœŸè¡Œä¸º â†’ é˜»å¡žå¼ withï¼ˆæ…¢ï¼Œä½†å¯é¢„æµ‹ï¼‰
        with _parse_lock:
            # T4-2: å·²æ‹¿åˆ°é”ã€è¿˜æ²¡è§£æž â€”â€” ã€ŒæŽ’é˜Ÿä¸­ã€åˆ°æ­¤ä¸ºæ­¢ï¼Œè¿›åº¦åˆ‡åˆ°ã€Œè§£æžä¸­ã€ã€‚
            # T3-1: å›žè°ƒ**è¿”å›ž False** è¡¨ç¤ºã€Œè¿™ä¸ªä»»åŠ¡åœ¨æŽ’é˜ŸæœŸé—´å·²è¢«å–æ¶ˆã€â†’ ç«‹åˆ»æ”¾å¼ƒï¼Œ
            # ä½ç½®å¿…é¡»åœ¨ `ParserOrchestrator()` ä¹‹å‰ï¼Œå¦åˆ™ç™½çƒ§ä¸€æ¬¡ doclingï¼ˆçº¦ 15 s + 3.5 GBï¼‰ã€‚
            # å‘åŽå…¼å®¹ï¼šè¿”å›ž None / å…¶å®ƒå€¼ â†’ ç…§å¸¸è§£æžï¼ˆåŒæ­¥è·¯ç”±æ ¹æœ¬ä¸ä¼  on_acquiredï¼‰ã€‚
            if on_acquired is not None and on_acquired() is False:
                raise ParseCancelled("æŽ’é˜ŸæœŸé—´å·²å–æ¶ˆï¼Œæœªè§£æž", stage="æŽ’é˜ŸæœŸé—´")

            orchestrator = ParserOrchestrator()
            parsed_result = orchestrator.parse_paper(str(pdf_path))

            # T2-3: å†™åº“å‰çš„æœ€åŽä¸€é“é—¸ã€‚docling æ˜¯é»‘ç›’è°ƒç”¨ï¼ˆåˆ†é’Ÿçº§ã€ä¸å¯ä¸­æ–­ï¼‰ï¼Œ
            # å–æ¶ˆåªèƒ½åœ¨è¿™é‡Œç”Ÿæ•ˆ â€”â€” è¿‡äº†è¿™ä¸€è¡Œå°±ä¸€å®šä¼šå†™åº“ã€‚
            if before_store is not None and before_store():
                raise ParseCancelled("ä»»åŠ¡å·²å–æ¶ˆï¼Œæœªå†™åº“", stage="è§£æžåŽ")

            if not DatabaseWriter().insert_paper(parsed_result):
                raise ParseStoreError("è§£æžæˆåŠŸä½†å†™å…¥æ•°æ®åº“å¤±è´¥")

            paper_id = parsed_result.get("paper_id", "")
            title = parsed_result.get("metadata", {}).get("title", filename)
            paragraph_count = len(parsed_result.get("paragraphs", []))

        return {
            "paper_id": paper_id,
            "title": title,
            "paragraph_count": paragraph_count,
            "stats": {
                "paragraphs": paragraph_count,
                "figures": len(parsed_result.get("figures", [])),
                "citations": len(parsed_result.get("citations", [])),
            },
        }



    return bp

