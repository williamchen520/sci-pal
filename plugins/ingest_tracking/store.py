"""PostgreSQL storage for the client ingest tracking plugin."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.db.pg_pool import admin_connection

MIGRATION = Path(__file__).resolve().parent / "migrations" / "001_ingest_tracking.sql"


def enabled() -> bool:
    return os.environ.get("SCIPAL_INGEST_TRACKING", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def ensure_schema() -> None:
    if not enabled():
        return
    sql = MIGRATION.read_text(encoding="utf-8")
    pg = admin_connection()
    try:
        for statement in sql.split(";"):
            if statement.strip():
                pg.execute(statement)
        pg.commit()
    finally:
        pg.close()


def create_batch(batch_id: str, source: str, total: int, meta: dict[str, Any] | None = None) -> None:
    pg = admin_connection()
    try:
        pg.execute(
            "INSERT INTO ingest_tracking_batches (batch_id,source,total,meta) "
            "VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT (batch_id) DO NOTHING",
            (batch_id, source, total, json.dumps(meta or {}, ensure_ascii=False)),
        )
        pg.commit()
    finally:
        pg.close()


def add_item(
    batch_id: str,
    filename: str,
    paper_id: str | None,
    quality_status: str,
    flags: list[dict[str, Any]] | None = None,
) -> int:
    pg = admin_connection()
    try:
        row = pg.execute(
            "INSERT INTO ingest_tracking_items "
            "(batch_id,filename,paper_id,quality_status,flags) "
            "VALUES (%s,%s,%s,%s,%s::jsonb) RETURNING id",
            (
                batch_id,
                filename,
                paper_id,
                quality_status,
                json.dumps(flags or [], ensure_ascii=False),
            ),
        ).fetchone()
        pg.commit()
        return int(row["id"])
    finally:
        pg.close()


def add_finding(
    batch_id: str,
    item_id: int | None,
    code: str,
    severity: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    pg = admin_connection()
    try:
        pg.execute(
            "INSERT INTO ingest_tracking_findings "
            "(batch_id,item_id,code,severity,message,detail) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
            (batch_id, item_id, code, severity, message, json.dumps(detail or {}, ensure_ascii=False)),
        )
        pg.commit()
    finally:
        pg.close()


def finish_batch(batch_id: str, summary: dict[str, int]) -> None:
    pg = admin_connection()
    try:
        pg.execute(
            "UPDATE ingest_tracking_batches SET status='finished', finished_at=now(), "
            "clean=%s, warning=%s, needs_review=%s, duplicate=%s, rejected=%s "
            "WHERE batch_id=%s",
            (
                summary.get("clean", 0),
                summary.get("warning", 0),
                summary.get("needs_review", 0),
                summary.get("duplicate", 0),
                summary.get("rejected", 0),
                batch_id,
            ),
        )
        pg.commit()
    finally:
        pg.close()


def get_batch(batch_id: str) -> dict[str, Any] | None:
    pg = admin_connection()
    try:
        batch = pg.execute(
            "SELECT * FROM ingest_tracking_batches WHERE batch_id=%s", (batch_id,)
        ).fetchone()
        if not batch:
            return None
        items = pg.execute(
            "SELECT * FROM ingest_tracking_items WHERE batch_id=%s ORDER BY id",
            (batch_id,),
        ).fetchall()
        findings = pg.execute(
            "SELECT * FROM ingest_tracking_findings WHERE batch_id=%s ORDER BY id",
            (batch_id,),
        ).fetchall()
        result = dict(batch)
        result["items"] = [dict(row) for row in items]
        result["findings"] = [dict(row) for row in findings]
        return result
    finally:
        pg.close()


def get_paper(paper_id: str) -> dict[str, Any] | None:
    pg = admin_connection()
    try:
        row = pg.execute(
            "SELECT paper_id, quality_status, quality_flags, quality_checked_at "
            "FROM papers WHERE paper_id=%s",
            (paper_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()


def review_paper(paper_id: str, status: str, flags: list[dict[str, Any]] | None = None) -> bool:
    pg = admin_connection()
    try:
        result = pg.execute(
            "UPDATE papers SET quality_status=%s, quality_flags=%s::jsonb, "
            "quality_checked_at=now() WHERE paper_id=%s",
            (status, json.dumps(flags or [], ensure_ascii=False), paper_id),
        )
        pg.commit()
        return result.rowcount > 0
    finally:
        pg.close()
