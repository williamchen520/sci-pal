"""Shared PDF parse service: one lock, one store path, one place to pick GROBID.

Extracted from ``routes/search_downloads.py``; both the sync and async parse
routes (``routes/papers_actions.py``) call :func:`parse_and_store`, so the
docling lock and the "parse then write" transaction live here.

GROBID endpoint selection
-------------------------
``grobid_mode`` chooses the service for this parse:

* ``auto`` / ``crf`` -> ``SCIPAL_GROBID_URL`` (default ``http://127.0.0.1:8070``)
* ``full``          -> ``SCIPAL_GROBID_URL_FULL`` (falls back to the CRF URL)
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, Dict

_parse_lock = threading.Lock()

# T3-3: 解析任务并发上限；超过直接 429，不做静默排队。
PARSE_MAX_CONCURRENT = 3

# 准入锁：只保护「查 running 数 + create_task」这一小段。
parse_admit_lock = threading.Lock()


class ParseStoreError(RuntimeError):
    """解析成功、但写库失败。"""


class ParseCancelled(RuntimeError):
    """任务已取消，本次解析放弃（数据不进库）。"""

    def __init__(self, message: str, stage: str = "") -> None:
        super().__init__(message)
        self.stage = stage


def parse_running_count(db_path: Path) -> int:
    """当前处于 running 的解析任务数。"""
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE type = 'parse_paper' AND status = 'running'"
        ).fetchone()[0]
    finally:
        conn.close()


def parse_and_store(
    db_path: Path,
    pdf_path,
    filename: str,
    before_store: Callable[[], bool] | None = None,
    on_acquired: Callable[[], bool] | None = None,
    on_waiting: Callable[[], None] | None = None,
    grobid_mode: str = "auto",
) -> Dict[str, Any]:
    """docling 解析 + 写库，全程持有同一把锁（串行化）。"""
    from build_db.db_writer import DatabaseWriter
    from build_db.parsers.parser_orchestrator import ParserOrchestrator
    from build_db.parsers.pipeline import resolve_grobid_url

    # 试抢一次判断「要不要排队」；必须在 import 之后（docling import 10~15s）。
    if on_waiting is not None:
        if _parse_lock.acquire(blocking=False):
            _parse_lock.release()
        else:
            on_waiting()

    with _parse_lock:
        if on_acquired is not None and on_acquired() is False:
            raise ParseCancelled("排队期间已取消，未解析", stage="排队期间")

        orchestrator = ParserOrchestrator(grobid_url=resolve_grobid_url(grobid_mode))
        parsed_result = orchestrator.parse_paper(str(pdf_path))

        if before_store is not None and before_store():
            raise ParseCancelled("任务已取消，未写库", stage="解析后")

        if not DatabaseWriter().insert_paper(parsed_result):
            raise ParseStoreError("解析成功但写入数据库失败")

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
            "parse_engine": parsed_result.get("metadata", {}).get("parse_engine", ""),
        },
    }
