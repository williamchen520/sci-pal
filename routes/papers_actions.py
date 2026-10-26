"""Papers routes: local scan / parse / pdf / supplementary / import / annotations."""

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

from flask import Blueprint, jsonify, request, send_from_directory

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


def build_papers_actions_blueprint(
    *,
    db_path: Path,
    project_root: Path,
    get_task_manager: Callable[[], Any],
    log: Any,
) -> Blueprint:
    bp = Blueprint("papers_actions", __name__)
    globals()["db_path_for_lookup"] = lambda: db_path
    globals()["DOCUMENTS_DIR"] = project_root / "documents"

    @bp.route("/api/papers/local", methods=["GET"])
    def list_local_papers():
        """æ‰«æ documents ç›®å½•ä¸‹æ‰€æœ‰ PDF æ–‡ä»¶ï¼Œäº¤å‰æŸ¥ papers è¡¨æ ‡è®°è§£æžçŠ¶æ€ã€‚

        Returns:
          papers: [{filename, file_size, modified_at, parsed, paper_id, title, authors, year, paragraph_count}]
        """
        import sqlite3

        if not DOCUMENTS_DIR.exists():
            # âš ï¸ çŠ¶æ€ç **ä¿æŒ 200**ï¼šå‰ç«¯ä¹Ÿåœ¨ç”¨è¿™ä¸ªè·¯ç”±ï¼Œè¿”å›ž 4xx å¯èƒ½è®©é¡µé¢æŠ¥é”™ã€‚
            # ã€Œç›®å½•ä¸å­˜åœ¨ã€ç”± MCP ä¾§ï¼ˆsearch_server.list_local_papersï¼‰æ® error å­—æ®µ
            # å¦‚å®žä¸ŠæŠ¥æˆ {"ok": false, ...}ï¼Œä¸å†ä¼ªè£…æˆã€Œ0 ç¯‡ã€ã€‚
            return jsonify({"papers": [], "error": "documents directory not found"}), 200

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # V25.17: æŸ¥è¯¢æ¯ç¯‡è®ºæ–‡çš„è¡¥å……ææ–™æ•°é‡
        supp_counts = {}
        try:
            supp_rows = conn.execute(
                "SELECT paper_id, COUNT(*) as cnt FROM supplementary_files GROUP BY paper_id"
            ).fetchall()
            for r in supp_rows:
                supp_counts[r["paper_id"]] = r["cnt"]
        except Exception:
            pass  # è¡¨å¯èƒ½è¿˜ä¸å­˜åœ¨ï¼ˆæ—§æ•°æ®åº“ï¼‰ï¼Œè¿ç§»ä¼šåœ¨å¯åŠ¨æ—¶åˆ›å»º

        # æ‰«æ documents ç›®å½•ã€‚æ¯ä¸ªæ–‡ä»¶åéƒ½èµ° _find_parsed_paperï¼ˆç»Ÿä¸€å£å¾„ï¼‰ï¼Œ
        # ä¸å†ç”¨ã€ŒåŽå†™è¦†ç›–ã€çš„ parsed_map â€”â€” å¦åˆ™ _mineru ç©ºå£³è¡Œä¼šæŠŠ 224 æ®µè¦†ç›–æˆ 0ã€‚
        result = []
        try:
            for entry in sorted(DOCUMENTS_DIR.iterdir()):
                if not entry.is_file() or entry.suffix.lower() != ".pdf":
                    continue
                filename = entry.name
                stat = entry.stat()
                info = _find_parsed_paper(filename, conn=conn)
                result.append({
                    "filename": filename,
                    "file_size": stat.st_size,
                    "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_at": stat.st_mtime,
                    "parsed": info is not None,
                    "paper_id": info["paper_id"] if info else None,
                    "title": (info["title"] or filename) if info else filename,
                    "authors": (info["authors"] or "") if info else "",
                    "year": info["year"] if info else None,
                    "paragraph_count": (info["total_paragraphs"] or 0) if info else 0,
                    "supp_count": supp_counts.get(info["paper_id"], 0) if info else 0,
                })
        finally:
            conn.close()

        # å·²è§£æžçš„æŽ’å‰é¢ï¼Œç„¶åŽæŒ‰æ–‡ä»¶å
        result.sort(key=lambda x: (not x["parsed"], x["filename"].lower()))
        return jsonify({"papers": result, "total": len(result), "parsed_count": sum(1 for p in result if p["parsed"])})


    # ============================================================
    # V33.2: åœ¨çº¿æ–‡çŒ®ä¸‹è½½ APIï¼ˆå¼‚æ­¥ä¸‹è½½+å¢žé‡å¯¼å…¥+å¢žé‡å»ºç´¢å¼•ï¼‰
    # ============================================================


    @bp.route("/api/papers/parse", methods=["POST"])
    def parse_local_paper():
        """V25.14: è§¦å‘è§£æžä¸€ç¯‡æœ¬åœ°æœªè§£æžçš„ PDF æ–‡çŒ®ã€‚

        Request body:
          filename: PDF æ–‡ä»¶åï¼ˆåœ¨ documents ç›®å½•ä¸‹ï¼‰

        Returns:
          paper_id, status, title, stats
        """
        data = request.get_json(silent=True) or {}
        filename = data.get("filename", "").strip()

        if not filename:
            return jsonify({"error": "ç¼ºå°‘ filename å‚æ•°"}), 400

        # é˜²æ­¢è·¯å¾„ç©¿è¶Š
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"error": "éžæ³•çš„æ–‡ä»¶å"}), 400

        pdf_path = DOCUMENTS_DIR / filename
        # T3-6: å…¥å‚æ ¡éªŒï¼ˆé¡ºåºå›ºå®šï¼‰ï¼šåŽç¼€ â†’ æ˜¯å¦æ™®é€šæ–‡ä»¶ã€‚
        # ä¼ ç›®å½•åæ—¶ exists() ä¸ºçœŸï¼Œä¼šä¸€è·¯åˆ° docling æ‰ç‚¸ï¼›ä¼  .txt ä¹Ÿä¼šç›´æŽ¥è¿›è§£æžã€‚
        # æ— åŽç¼€çš„åå­—ï¼ˆå¤šä¸ºç›®å½•åï¼Œå¦‚ `docs`ï¼‰å½’åˆ°ã€Œä¸æ˜¯æ™®é€šæ–‡ä»¶ã€â€”â€”æŠ¥ 404 æ¯”
        # æŠ¥ã€Œåªæ”¯æŒ .pdfã€æ›´å‡†ç¡®ï¼Œä¹Ÿä¸Žå·¥å• T3-6-a çš„åˆ¤æ®ä¸€è‡´ã€‚
        suffix = pdf_path.suffix.lower()
        if suffix != ".pdf":
            if suffix:
                return jsonify({"error": f"åªæ”¯æŒ .pdf æ–‡ä»¶: {filename}"}), 400
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨æˆ–ä¸æ˜¯æ™®é€šæ–‡ä»¶: {filename}"}), 404
        if not pdf_path.is_file():
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨æˆ–ä¸æ˜¯æ™®é€šæ–‡ä»¶: {filename}"}), 404

        # T3-3: æœ¬è·¯ç”±**æœ‰æ„ä¸åšå¹¶å‘å‡†å…¥**ï¼ˆä¸æ˜¯æ¼äº†ï¼‰ã€‚å‰ç«¯ã€Œè§£æžã€æŒ‰é’®æ˜¯äººç‚¹çš„ï¼Œ
        # åŠ  429 åªä¼šè®©é¡µé¢èŽ«åæŠ¥é”™ï¼›å¹¶å‘é¢åº¦ç”±å¼‚æ­¥è·¯ç”± parse_async å…œä½ã€‚
        # ä¸¤æ¡è·¯ç”±å…±ç”¨ _parse_and_store é‡Œçš„ _parse_lockï¼Œä¸ä¼šçœŸå¹¶è¡Œè·‘ä¸¤ä¸ª doclingã€‚

        # æ£€æŸ¥æ˜¯å¦å·²è§£æžã€‚ç»Ÿä¸€å£å¾„ï¼šæ®µè½æ•°å¤šè€…ä¼˜å…ˆã€å¹¶åˆ—å–åˆ›å»ºæ›´æ—©çš„
        # ï¼ˆpapers.filename ä¸å”¯ä¸€ï¼ŒåŒä¸€æ–‡ä»¶å¯èƒ½æœ‰ `<id>` ä¸Ž `<id>_mineru` ä¸¤è¡Œï¼‰
        row = _find_parsed_paper(filename)

        if row:
            # å·²è§£æžï¼Œç›´æŽ¥è¿”å›ž
            return jsonify({
                "paper_id": row["paper_id"],
                "status": "already_parsed",
                "title": row["title"] or filename,
                "paragraph_count": row["total_paragraphs"] or 0,
            })

        # æœªè§£æžï¼Œæ‰§è¡Œè§£æž
        print(f"ðŸ“„ å¼€å§‹è§£æž: {filename}")

        # å…ˆæ£€æŸ¥ build_db ç›®å½•æ˜¯å¦å­˜åœ¨
        build_db_dir = project_root / "build_db"
        if not build_db_dir.exists():
            return jsonify({"error": f"è§£æžå¤±è´¥: build_db ç›®å½•ä¸å­˜åœ¨ ({build_db_dir})ï¼Œè¯·ç¡®è®¤é¡¹ç›®ç»“æž„å®Œæ•´"}), 500

        try:
            # ä¸Žå¼‚æ­¥è·¯ç”±å…±ç”¨åŒä¸€æŠŠé”ï¼ˆ_parse_and_store å†…éƒ¨æŒæœ‰ï¼‰ï¼Œ
            # å‰ç«¯ã€Œè§£æžã€æŒ‰é’®ä¸Ž MCP æäº¤ä¸ä¼šå†æœ‰ä¸¤æ¬¡ docling å¹¶å‘ã€‚
            result = _parse_and_store(pdf_path, filename)
        except ParseStoreError:
            # å­—æ®µä¸Žæ–‡æ¡ˆä¿æŒåŽŸæ ·ï¼ˆå‰ç«¯æŒ‰ error å±•ç¤ºï¼‰
            return jsonify({"error": "è§£æžæˆåŠŸä½†å†™å…¥æ•°æ®åº“å¤±è´¥"}), 500
        except ImportError as e:
            # å¯¼å…¥å¤±è´¥æ—¶ç»™å‡ºæ›´æ˜Žç¡®çš„è¯Šæ–­ï¼›æ­¤æ—¶å°šæœªå–é”ï¼Œä¸ä¼šå¡ä½é˜Ÿåˆ—
            import traceback
            print(f"âŒ è§£æžæ¨¡å—å¯¼å…¥å¤±è´¥: {e}")
            traceback.print_exc()
            return jsonify({"error": f"è§£æžæ¨¡å—å¯¼å…¥å¤±è´¥: {str(e)}ã€‚è¯·ç¡®è®¤ build_db/ ç›®å½•å®Œæ•´ä¸” docling å·²å®‰è£…ï¼ˆpip install doclingï¼‰"}), 500
        except Exception as e:
            print(f"âŒ è§£æžå¤±è´¥: {filename} - {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"è§£æžå¤±è´¥: {str(e)}"}), 500

        print(f"âœ… è§£æžå®Œæˆ: {result['title']} ({result['paragraph_count']} æ®µè½)")
        return jsonify({
            "paper_id": result["paper_id"],
            "status": "parsed",
            "title": result["title"],
            "paragraph_count": result["paragraph_count"],
            "stats": result["stats"],
        })


    @bp.route("/api/papers/parse_async", methods=["POST"])
    def parse_local_paper_async():
        """V33.17-6B: å¼‚æ­¥è§£æžæœ¬åœ° PDFï¼ˆç«‹å³è¿”å›ž task_idï¼‰ã€‚

        å‚æ•°ä¸ŽåŒæ­¥ç‰ˆ `/api/papers/parse` å®Œå…¨ä¸€è‡´ï¼šJSON body çš„ `filename`ã€‚

        æ ¡éªŒé¡ºåºï¼ˆ**ä¾¿å®œæ ¡éªŒå¿…é¡»åœ¨è¿”å›ž task_id ä¹‹å‰**ï¼Œè®©æ¨¡åž‹ç«‹åˆ»çŸ¥é“å‚æ•°é”™äº†ï¼‰ï¼š
          1. `filename` ä¸ºç©º              â†’ 400
          2. å« `..` / `/` / `\\`         â†’ 400ï¼ˆè·¯å¾„ç©¿è¶Šï¼‰
          3. åŽç¼€ä¸æ˜¯ `.pdf`              â†’ 400
          4. ä¸æ˜¯æ™®é€šæ–‡ä»¶ï¼ˆä¸å­˜åœ¨/æ˜¯ç›®å½•ï¼‰â†’ 404
          ä»¥ä¸Šå››æ¡éƒ½åœ¨ `create_task()` ä¹‹å‰åˆ¤æŽ‰ã€‚
        å¹¶å‘å‡†å…¥ï¼ˆT3-3ï¼‰ï¼šrunning çš„ `parse_paper` ä»»åŠ¡è¾¾åˆ° `PARSE_MAX_CONCURRENT`ï¼ˆ3ï¼‰
          â†’ **429** + `{error, running, limit}`ï¼Œä¸”**ä¸å»ºä»»åŠ¡è¡Œ**ã€‚ä¸æŽ’é˜Ÿã€ä¸é™é»˜ç­‰å¾…ã€‚

        åŽå°çº¿ç¨‹ï¼š
          Â· å·²è§£æžï¼ˆ`_find_parsed_paper` å‘½ä¸­ï¼Œæ®µè½æ•°å¤šè€…ä¼˜å…ˆï¼‰â†’ **ç§’çº§**
            `complete_task({"status":"already_parsed", ...})`
          Â· æœªè§£æž â†’ `_parse_and_store()`ï¼ˆå†…éƒ¨æŒæœ‰ `_parse_lock`ï¼Œä¸ŽåŒæ­¥è·¯ç”±å…±ç”¨ï¼‰â†’
            `complete_task({"status":"parsed", ...})`
          Â· å¤±è´¥ â†’ `fail_task(task_id, str(e)[:500])`

        âš ï¸ å–æ¶ˆè¯­ä¹‰ï¼ˆå¦‚å®žè¯´æ˜Žï¼‰ï¼š
          **docling æœŸé—´æ— æ³•ä¸­æ–­**ã€‚å–æ¶ˆåœ¨ä¸‰ä¸ªç‚¹ç”Ÿæ•ˆï¼š
            1. æäº¤åŽã€æ‹¿é”å‰ï¼ˆ`is_cancelled`ï¼‰ï¼›
            2. **æ‹¿åˆ°é”ã€è¿˜æ²¡è§£æž**ï¼ˆT3-1 çš„ `on_acquired`ï¼‰â€”â€” æŽ’é˜ŸæœŸé—´å–æ¶ˆçš„è¯ï¼Œ
               è¿™é‡Œç›´æŽ¥æ”¾å¼ƒï¼Œ**è¿ž docling éƒ½ä¸è·‘**ï¼ˆä¸å†ç™½çƒ§ä¸€æ¬¡è§£æžï¼‰ï¼›
            3. **å†™åº“ä¹‹å‰**ï¼ˆ`_parse_and_store` çš„ `before_store`ï¼‰â€”â€”
               è§£æžå·²è·‘å®Œæ—¶å–æ¶ˆï¼Œä»ç„¶ä¸å†™åº“ã€‚
          è‹¥è¯·æ±‚åˆ°è¾¾æ—¶å·²ç»è¿‡äº†ã€Œå†™åº“ç‚¹ã€ï¼Œæ•°æ®ä¼šä¿ç•™ã€ä»»åŠ¡å¯èƒ½ä»æ˜¯ `completed`ã€‚

        âš ï¸ èƒ½åŠ›è¾¹ç•Œï¼ˆå¦‚å®žå‘ŠçŸ¥æ¨¡åž‹ï¼‰ï¼š
          Â· åªèƒ½è§£æž `documents/` ä¸‹**å·²å­˜åœ¨**çš„ PDFï¼›æœ¬ç«¯ç‚¹**ä¸èƒ½ä¸Šä¼ **æ–‡ä»¶ï¼ˆMCP ä¼ ä¸äº† multipartï¼‰ã€‚
          Â· `insert_paper` **ä¸å†™ ChromaDB** â†’ è§£æžå…¥åº“åŽ**ä¸ä¿è¯ç«‹åˆ»è¢«æ··åˆæ£€ç´¢å‘½ä¸­**ï¼Œ
            ä½†å¯ä»¥æŒ‰ `paper_id` æŸ¥åˆ°è¯¦æƒ…ã€ä¹Ÿèƒ½è¿›å›¾è°±ã€‚
          Â· ä»»åŠ¡ä¸Ž review ä»»åŠ¡åŒè¡¨ï¼Œç”¨ `review_task_status`ï¼ˆ`/api/review/task/<id>`ï¼‰è½®è¯¢ã€‚
        """
        data = request.get_json(silent=True) or {}
        filename = str(data.get("filename", "")).strip()

        # ===== åŒæ­¥æ ¡éªŒï¼ˆå¿…é¡»åœ¨ create_task ä¹‹å‰ï¼‰=====
        if not filename:
            return jsonify({"error": "ç¼ºå°‘ filename å‚æ•°"}), 400
        if ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"error": "éžæ³•çš„æ–‡ä»¶å"}), 400

        pdf_path = DOCUMENTS_DIR / filename
        # T3-6: ä¸ŽåŒæ­¥è·¯ç”±åŒä¸€å¥—æ ¡éªŒï¼ˆåŽç¼€ â†’ æ™®é€šæ–‡ä»¶ï¼‰ï¼Œä¸”éƒ½åœ¨å»ºä»»åŠ¡ä¹‹å‰ã€‚
        # æ— åŽç¼€ â†’ 404ã€Œä¸æ˜¯æ™®é€šæ–‡ä»¶ã€ï¼›æœ‰éž .pdf åŽç¼€ â†’ 400ã€Œåªæ”¯æŒ .pdfã€ã€‚
        suffix = pdf_path.suffix.lower()
        if suffix != ".pdf":
            if suffix:
                return jsonify({"error": f"åªæ”¯æŒ .pdf æ–‡ä»¶: {filename}"}), 400
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨æˆ–ä¸æ˜¯æ™®é€šæ–‡ä»¶: {filename}"}), 404
        if not pdf_path.is_file():
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨æˆ–ä¸æ˜¯æ™®é€šæ–‡ä»¶: {filename}"}), 404

        # T3-3: å¹¶å‘å‡†å…¥ã€‚ã€ŒæŸ¥ running æ•°ã€ä¸Žã€Œcreate_taskã€å¿…é¡»åœ¨åŒä¸€æŠŠçŸ­é”é‡Œï¼Œ
        # å¦åˆ™ä¸¤ä¸ªè¯·æ±‚å¯èƒ½åŒæ—¶è¯»åˆ° running=2 éƒ½æ”¾è¡Œã€‚è¶…é™**ä¸å»ºä»»åŠ¡è¡Œ**ã€‚
        with _parse_admit_lock:
            running = _parse_running_count()
            if running >= PARSE_MAX_CONCURRENT:
                return jsonify({
                    "error": f"è§£æžä»»åŠ¡å·²è¾¾ä¸Šé™ï¼ˆ{PARSE_MAX_CONCURRENT}ï¼‰ï¼Œè¯·ç­‰å‰é¢çš„å®Œæˆæˆ–å–æ¶ˆ",
                    "running": running,
                    "limit": PARSE_MAX_CONCURRENT,
                }), 429
            # T3-4: params è½åº“ï¼Œæ–¹ä¾¿äº‹åŽæŒ‰æ–‡ä»¶åå®šä½ä»»åŠ¡ï¼ˆget_task ä»åªè¿”å›ž 7 é”®ï¼‰
            task_id = get_task_manager().create_task("parse_paper", params={"filename": filename})

        def _fail(error_text: str) -> None:
            """ç½® failedï¼Œå¹¶æŠŠ progress ä»Žä¸Šä¸€é˜¶æ®µï¼ˆå¦‚ã€Œå†™å…¥æ•°æ®åº“â€¦ã€ï¼‰æ”¹æŽ‰ã€‚

            V33.17: å¿…é¡»**å…ˆ**æ”¹ progress å† fail â€”â€” `update_progress` ä¸Ž `fail_task`
            éƒ½å¸¦ `WHERE status='running'`ï¼Œé¡ºåºåäº†å°±æ”¹ä¸åŠ¨ï¼Œå‰ç«¯ä¼šçœ‹åˆ°
            `status=failed | progress=å†™å…¥æ•°æ®åº“â€¦` è¿™ç§è‡ªç›¸çŸ›ç›¾çš„ç»„åˆã€‚
            """
            get_task_manager().update_progress(task_id, "å·²å¤±è´¥")
            get_task_manager().fail_task(task_id, error_text)

        def _on_acquired() -> bool:
            """æ‹¿åˆ°é”ã€å°šæœªè§£æžï¼ˆT3-1ï¼‰ã€‚

            è¿”å›ž **False** = æŽ’é˜ŸæœŸé—´å·²è¢«å–æ¶ˆ â†’ `_parse_and_store` ä¼šåœ¨æž„é€ 
            `ParserOrchestrator()` ä¹‹å‰æ”¾å¼ƒï¼Œ**ä¸è·‘ docling**ã€‚
            è¿”å›ž True = æ­£å¸¸ï¼Œé¡ºå¸¦æŠŠ progress åˆ‡åˆ°ã€Œè§£æžä¸­ã€ã€‚
            """
            if get_task_manager().is_cancelled(task_id):
                return False
            get_task_manager().update_progress(task_id, "è§£æžä¸­ï¼ˆdoclingï¼‰â€¦")
            return True

        def _before_store() -> bool:
            """å†™åº“å‰çš„æœ€åŽä¸€é“é—¸ï¼ˆåœ¨ _parse_and_store çš„é”å†…ã€è§£æžå®ŒæˆåŽè¢«è°ƒç”¨ï¼‰ã€‚

            è¿”å›ž True = æ”¾å¼ƒå†™åº“ã€‚é¡ºå¸¦æŠŠ progress æŽ¨è¿›åˆ°ã€Œå†™å…¥æ•°æ®åº“â€¦ã€â€”â€”
            æ­¤åˆ»ä»»åŠ¡çŠ¶æ€ä»æ˜¯ runningï¼Œ`update_progress` å†™å¾—è¿›åŽ»ã€‚
            """
            if get_task_manager().is_cancelled(task_id):
                return True
            get_task_manager().update_progress(task_id, "å†™å…¥æ•°æ®åº“â€¦")
            return False

        def run_task():
            try:
                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                # â”€â”€ å¿«è·¯å¾„ï¼šå·²è§£æžï¼Œç§’çº§è¿”å›žï¼ˆç»Ÿä¸€å£å¾„ï¼Œè§ _find_parsed_paperï¼‰â”€â”€
                row = _find_parsed_paper(filename)
                if row:
                    get_task_manager().complete_task(task_id, {
                        "paper_id": row["paper_id"],
                        "status": "already_parsed",
                        "title": row["title"] or filename,
                        "paragraph_count": row["total_paragraphs"] or 0,
                    })
                    return

                # â”€â”€ æ…¢è·¯å¾„ â”€â”€
                if get_task_manager().is_cancelled(task_id):
                    get_task_manager().cancel_task(task_id)
                    return

                # T4-2: ä¸¤æ¡è¿›åº¦éƒ½ç”± _parse_and_store å›žè°ƒå†™ï¼Œæ—¶æœºæ‰å‡†ï¼š
                #   on_waiting  â€”â€” è¯•æŠ¢é”å¤±è´¥ï¼ˆçœŸçš„è¦æŽ’é˜Ÿï¼‰â†’ ã€ŒæŽ’é˜Ÿä¸­ã€
                #   on_acquired â€”â€” çœŸæ­£æ‹¿åˆ°é”ï¼ˆå¼€å§‹è§£æžï¼‰  â†’ ã€Œè§£æžä¸­ï¼ˆdoclingï¼‰â€¦ã€
                # ä»¥å‰è¿™é‡Œæ— æ¡ä»¶å†™ã€Œè§£æžä¸­ã€ï¼Œç´§æŽ¥å°±é˜»å¡žåœ¨é”ä¸Š â†’ æŽ’é˜Ÿä¸å¯è§‚æµ‹ï¼›
                # è¯•æŠ¢ä¹Ÿä¸èƒ½æ”¾åœ¨è·¯ç”±å±‚ï¼š_parse_and_store é‡Œçš„ docling import é¦–æ¬¡è¦
                # 10~15 ç§’ï¼Œé‚£æ—¶é”è¿˜æ˜¯ç©ºçš„ï¼Œä¼šæ¼æŠ¥æŽ’é˜Ÿã€‚
                result = _parse_and_store(
                    pdf_path,
                    filename,
                    before_store=_before_store,
                    on_waiting=lambda: get_task_manager().update_progress(
                        task_id, "æŽ’é˜Ÿä¸­ï¼ˆå‰é¢è¿˜æœ‰è§£æžä»»åŠ¡ï¼‰"
                    ),
                    on_acquired=_on_acquired,
                )

                get_task_manager().complete_task(task_id, {
                    "paper_id": result["paper_id"],
                    "status": "parsed",
                    "title": result["title"],
                    "paragraph_count": result["paragraph_count"],
                    "stats": result["stats"],
                })
            except ParseCancelled as exc:
                # å·²å–æ¶ˆ â†’ æ•°æ®æ²¡å†™åº“ã€‚çŠ¶æ€ç”±å–æ¶ˆç«¯ç‚¹ç½®ä¸º cancelledï¼Œè¿™é‡Œåªç•™æ—¥å¿—ã€‚
                get_task_manager().cancel_task(task_id)  # å·²æ˜¯ cancelled æ—¶ rowcount=0ï¼Œå¹‚ç­‰
                # flush=Trueï¼šè¿›ç¨‹è¢« kill æ—¶ stdout æ˜¯å—ç¼“å†²ï¼Œè¿™è¡Œä¼šä¸¢ï¼›è¿™æ¡æ—¥å¿—æ˜¯
                # ã€Œå–æ¶ˆç¡®å®žæ²¡å†™åº“ã€çš„å”¯ä¸€çŽ°åœºè¯æ®ï¼Œä¸èƒ½æŒ‡æœ›ç¼“å†²åŒºã€‚
                # T3-1: é˜¶æ®µç”± ParseCancelled.stage ç»™å‡ºï¼ˆæŽ’é˜ŸæœŸé—´ / è§£æžåŽï¼‰
                print(
                    f"[INFO] è§£æžå·²å–æ¶ˆï¼ˆ{exc.stage or 'æœªçŸ¥é˜¶æ®µ'}ï¼‰ï¼Œæœªå†™åº“ï¼š"
                    f"{filename}ï¼ˆ{task_id}ï¼‰",
                    flush=True,
                )
            except ParseStoreError as e:
                _fail(str(e))
            except Exception as e:
                print(f"[ERROR] Async parse failed: {filename} - {e}")
                import traceback
                traceback.print_exc()
                # ä¸è¦æŠŠæ•´æ®µ traceback å¡žè¿› DB
                _fail(str(e)[:500])

        threading.Thread(target=run_task, daemon=True).start()
        return jsonify({"task_id": task_id})


    @bp.route("/api/papers/<paper_id>/pdf", methods=["GET"])
    def serve_pdf(paper_id):
        """Serve the original PDF file for a paper (for built-in PDF reader)."""
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT filename FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        conn.close()
        if not row or not row["filename"]:
            return jsonify({"error": "PDF not found"}), 404

        pdf_path = DOCUMENTS_DIR / row["filename"]
        if not pdf_path.exists():
            return jsonify({"error": f"PDF file missing: {row['filename']}"}), 404

        return send_from_directory(
            str(DOCUMENTS_DIR), row["filename"],
            mimetype="application/pdf")


    # ============================================================
    # V26.4: Abstract API - æ ¹æ® PMID æŸ¥è¯¢æ‘˜è¦
    # ============================================================

    # ============================================================
    # V25.17: Supplementary files API
    # ============================================================

    @bp.route("/api/papers/<paper_id>/supplementary", methods=["GET"])
    def list_supplementary_files(paper_id):
        """List all supplementary files for a paper."""
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        return jsonify({"supplementary_files": files})


    @bp.route("/api/papers/<paper_id>/supplementary", methods=["POST"])
    def upload_supplementary_file(paper_id):
        """Upload a supplementary file and associate it with a paper.
    
        Request: multipart/form-data with 'file' field and optional 'description'
        """
        import uuid
        from build_db.db_writer import DatabaseWriter

        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        uploaded = request.files['file']
        if not uploaded.filename:
            return jsonify({"error": "Empty filename"}), 400

        # Verify paper exists
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"error": f"Paper {paper_id} not found"}), 404

        # Save file to documents directory
        original_filename = uploaded.filename
        # Handle duplicate filenames
        save_name = original_filename
        base, ext = os.path.splitext(original_filename)
        counter = 1
        while (DOCUMENTS_DIR / save_name).exists():
            save_name = f"{base}_{counter}{ext}"
            counter += 1

        save_path = DOCUMENTS_DIR / save_name
        uploaded.save(str(save_path))
        file_size = save_path.stat().st_size

        # Determine file type
        file_type = ext.lower().lstrip('.') or 'unknown'

        # Generate supp_id
        supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

        # Get description from form
        description = request.form.get('description', '')

        # Save to database
        writer = DatabaseWriter()
        success = writer.insert_supplementary_file({
            "supp_id": supp_id,
            "paper_id": paper_id,
            "filename": save_name,
            "file_type": file_type,
            "file_path": str(save_path),
            "file_size": file_size,
            "description": description,
        })

        if not success:
            # Clean up file if DB insert failed
            save_path.unlink(missing_ok=True)
            return jsonify({"error": "Failed to save supplementary file record"}), 500

        print(f"ðŸ“Ž Supplementary file added: {save_name} -> {paper_id}")
        return jsonify({
            "success": True,
            "supp_id": supp_id,
            "filename": save_name,
            "file_type": file_type,
            "file_size": file_size,
        })


    @bp.route("/api/papers/<paper_id>/supplementary/<supp_id>/download", methods=["GET"])
    def download_supplementary_file(paper_id, supp_id):
        """Download/serve a supplementary file."""
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        target = next((f for f in files if f["supp_id"] == supp_id), None)
        if not target:
            return jsonify({"error": "Supplementary file not found"}), 404

        file_path = Path(target["file_path"])
        if not file_path.exists():
            return jsonify({"error": f"File missing: {target['filename']}"}), 404

        return send_from_directory(
            str(file_path.parent), file_path.name,
            as_attachment=False)


    @bp.route("/api/papers/<paper_id>/supplementary/<supp_id>", methods=["DELETE"])
    def delete_supplementary_file(paper_id, supp_id):
        """Delete a supplementary file record and optionally the file itself.
    
        Query param: delete_file=1 to also delete the actual file
        """
        from build_db.db_writer import DatabaseWriter
        writer = DatabaseWriter()
        files = writer.get_supplementary_files(paper_id)
        target = next((f for f in files if f["supp_id"] == supp_id), None)
        if not target:
            return jsonify({"error": "Supplementary file not found"}), 404

        # Delete DB record
        success = writer.delete_supplementary_file(supp_id)
        if not success:
            return jsonify({"error": "Failed to delete record"}), 500

        # Optionally delete actual file
        delete_file = request.args.get('delete_file', '0') == '1'
        if delete_file:
            file_path = Path(target["file_path"])
            if file_path.exists():
                file_path.unlink()
                print(f"ðŸ—‘ï¸  Supplementary file deleted: {target['filename']}")

        return jsonify({"success": True, "supp_id": supp_id})


    # ============================================================
    # V25.17: å¯¼å…¥æ–‡çŒ®ï¼ˆæ­£æ–‡ + å¯é€‰è¡¥å……ææ–™ï¼Œä¸€æ¬¡ä¸Šä¼ ï¼‰
    # ============================================================

    @bp.route("/api/papers/import", methods=["POST"])
    def import_paper():
        """å¯¼å…¥ä¸€ç¯‡æ–‡çŒ®ï¼šæ­£æ–‡PDFï¼ˆå¿…é€‰ï¼‰+ è¡¥å……ææ–™ï¼ˆå¯é€‰ï¼Œå¤šé€‰ï¼‰ã€‚

        åªè´Ÿè´£ä¿å­˜æ–‡ä»¶åˆ° documents ç›®å½•ï¼Œä¸è§¦å‘è§£æžã€‚
        å‰ç«¯æ‹¿åˆ° filename åŽå†è°ƒç”¨ /api/papers/parse è§¦å‘è§£æžï¼Œ
        è§£æžå®ŒæˆåŽç”¨ paper_id æŠŠè¡¥å……ææ–™é€ä¸ªå…³è”ã€‚

        Request: multipart/form-data
          - paper: æ­£æ–‡ PDF æ–‡ä»¶ï¼ˆå¿…é€‰ï¼‰
          - supplementary: è¡¥å……ææ–™æ–‡ä»¶ï¼ˆå¯é€‰ï¼Œå¯å¤šä¸ªåŒåå­—æ®µï¼‰
        """
        import uuid

        # æ­£æ–‡ PDFï¼ˆå¿…é€‰ï¼‰
        if 'paper' not in request.files:
            return jsonify({"error": "ç¼ºå°‘æ­£æ–‡ PDF æ–‡ä»¶ï¼ˆpaper å­—æ®µï¼‰"}), 400

        paper_file = request.files['paper']
        if not paper_file.filename:
            return jsonify({"error": "æ­£æ–‡æ–‡ä»¶åä¸ºç©º"}), 400

        # ä¿å­˜æ­£æ–‡ PDFï¼ˆå¤„ç†é‡åï¼‰
        paper_filename = paper_file.filename
        base, ext = os.path.splitext(paper_filename)
        counter = 1
        while (DOCUMENTS_DIR / paper_filename).exists():
            paper_filename = f"{base}_{counter}{ext}"
            counter += 1
        paper_file.save(str(DOCUMENTS_DIR / paper_filename))
        paper_size = (DOCUMENTS_DIR / paper_filename).stat().st_size
        print(f"ðŸ“¥ å¯¼å…¥æ­£æ–‡: {paper_filename} ({paper_size / 1024:.0f} KB)")

        # è¡¥å……ææ–™ï¼ˆå¯é€‰ï¼Œå¤šé€‰ï¼‰
        supp_files = request.files.getlist('supplementary')
        saved_supp = []
        for supp_file in supp_files:
            if not supp_file.filename:
                continue
            # ä¿å­˜è¡¥å……ææ–™ï¼ˆå¤„ç†é‡åï¼‰
            supp_filename = supp_file.filename
            s_base, s_ext = os.path.splitext(supp_filename)
            s_counter = 1
            while (DOCUMENTS_DIR / supp_filename).exists():
                supp_filename = f"{s_base}_{s_counter}{s_ext}"
                s_counter += 1
            supp_file.save(str(DOCUMENTS_DIR / supp_filename))
            supp_size = (DOCUMENTS_DIR / supp_filename).stat().st_size
            file_type = s_ext.lower().lstrip('.') or 'unknown'
            saved_supp.append({
                "filename": supp_filename,
                "original_name": supp_file.filename,
                "file_type": file_type,
                "file_size": supp_size,
            })
            print(f"ðŸ“Ž å¯¼å…¥è¡¥å……ææ–™: {supp_filename} ({supp_size / 1024:.0f} KB)")

        return jsonify({
            "success": True,
            "paper_filename": paper_filename,
            "paper_size": paper_size,
            "supplementary_files": saved_supp,
            "supplementary_count": len(saved_supp),
        })


    @bp.route("/api/papers/<paper_id>/supplementary/link", methods=["POST"])
    def link_supplementary_file(paper_id):
        """å°† documents ç›®å½•ä¸­å·²å­˜åœ¨çš„æ–‡ä»¶å…³è”ä¸ºæŸç¯‡è®ºæ–‡çš„è¡¥å……ææ–™ã€‚
        ç”¨äºŽå¯¼å…¥æµç¨‹ï¼šæ–‡ä»¶å·²é€šè¿‡ /api/papers/import ä¸Šä¼ ï¼Œè§£æžå¾—åˆ° paper_id åŽï¼Œ
        æŒ‰æ–‡ä»¶åç›´æŽ¥å…³è”ï¼Œä¸éœ€è¦é‡æ–°ä¸Šä¼ æ–‡ä»¶å†…å®¹ã€‚

        Request body: {"filename": "xxx.pdf", "description": "..."}
        """
        import uuid
        from build_db.db_writer import DatabaseWriter

        data = request.get_json(force=True)
        filename = data.get('filename', '')
        description = data.get('description', '')

        if not filename:
            return jsonify({"error": "ç¼ºå°‘ filename"}), 400

        # éªŒè¯è®ºæ–‡å­˜åœ¨
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT paper_id FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"error": f"Paper {paper_id} not found"}), 404

        # éªŒè¯æ–‡ä»¶å­˜åœ¨
        file_path = DOCUMENTS_DIR / filename
        if not file_path.exists():
            return jsonify({"error": f"æ–‡ä»¶ä¸å­˜åœ¨: {filename}"}), 404

        file_size = file_path.stat().st_size
        file_type = file_path.suffix.lower().lstrip('.') or 'unknown'
        supp_id = f"supp_{paper_id}_{uuid.uuid4().hex[:8]}"

        writer = DatabaseWriter()
        success = writer.insert_supplementary_file({
            "supp_id": supp_id,
            "paper_id": paper_id,
            "filename": filename,
            "file_type": file_type,
            "file_path": str(file_path),
            "file_size": file_size,
            "description": description,
        })

        if not success:
            return jsonify({"error": "æ•°æ®åº“å†™å…¥å¤±è´¥"}), 500

        print(f"ðŸ”— è¡¥å……ææ–™å…³è”: {filename} -> {paper_id}")
        return jsonify({
            "success": True,
            "supp_id": supp_id,
            "filename": filename,
            "file_type": file_type,
            "file_size": file_size,
        })


    # V25.10: PDF æ ‡æ³¨ï¼ˆæ·»åŠ /åˆ é™¤æ³¨é‡Šï¼Œå†™å…¥ PDF æ–‡ä»¶æŒä¹…åŒ–ï¼‰
    @bp.route("/api/papers/<paper_id>/annotate", methods=["POST"])
    def annotate_pdf(paper_id):
        """æ·»åŠ æˆ–åˆ é™¤ PDF æ³¨é‡Šã€‚æ³¨é‡Šç›´æŽ¥å†™å…¥ PDF æ–‡ä»¶ã€‚

        Request body:
          action: "add" | "delete"
          page: é¡µç ï¼ˆä»Ž1å¼€å§‹ï¼‰
          type: "highlight" | "underline" | "text"
          rect: [x0, y0, x1, y1] PDFæ ‡å‡†åæ ‡ï¼ˆå·¦ä¸‹åŽŸç‚¹ï¼‰
          color: [r, g, b] å¯é€‰ï¼Œ0-1
          text: æ³¨é‡Šæ–‡æœ¬ å¯é€‰
        """
        from services.pdf.annotator import PdfAnnotator

        data = request.get_json(silent=True) or {}
        action = data.get("action", "add")
        page = data.get("page")
        annot_type = data.get("type")
        rect = data.get("rect")
        color = data.get("color")
        text = data.get("text", "")

        if not page or not annot_type or not rect:
            return jsonify({"error": "ç¼ºå°‘å¿…è¦å‚æ•°: page, type, rect"}), 400

        annotator = PdfAnnotator(str(db_path), str(DOCUMENTS_DIR))

        if action == "delete":
            result = annotator.delete_annotation(paper_id, page, annot_type, rect, text)
        else:
            result = annotator.add_annotation(paper_id, page, annot_type, rect, color, text)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "æ ‡æ³¨æ“ä½œå¤±è´¥")}), 500

        return jsonify(result)


    # V25.10: åˆ—å‡º PDF ä¸­çš„æ ‡æ³¨
    @bp.route("/api/papers/<paper_id>/annotations", methods=["GET"])
    def list_pdf_annotations(paper_id):
        """åˆ—å‡º PDF ä¸­çš„æ‰€æœ‰æ ‡æ³¨ï¼ˆç”¨äºŽå‰ç«¯æ¸²æŸ“å¯ç‚¹å‡»çš„åˆ é™¤è¦†ç›–å±‚ï¼‰ã€‚

        Query params:
          page: é¡µç ï¼ˆå¯é€‰ï¼Œä¸å¡«åˆ™åˆ—å‡ºæ‰€æœ‰é¡µï¼‰
        """
        from services.pdf.annotator import PdfAnnotator

        page = request.args.get("page", type=int)
        annotator = PdfAnnotator(str(db_path), str(DOCUMENTS_DIR))
        result = annotator.list_annotations(paper_id, page)

        if not result.get("success"):
            return jsonify({"error": result.get("error", "èŽ·å–æ ‡æ³¨åˆ—è¡¨å¤±è´¥")}), 500

        return jsonify(result)


    # ---------------------------------------------------------------------------
    # Frontend
    # ---------------------------------------------------------------------------


    return bp

