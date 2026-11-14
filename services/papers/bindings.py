"""Bind a paper code link to an existing code RAG library."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import psycopg

from services.db.pg_pool import corpus_connection, owner_connection


def _binding_id(paper_id: str, link_id: str) -> str:
    digest = hashlib.sha256(f"{paper_id}\0{link_id}".encode("utf-8")).hexdigest()[:16]
    return f"bind_{digest}"


def _code_dsn() -> str:
    return os.environ.get("SCIPAL_CODE_READ_DSN", "").strip() or os.environ.get("SCIPAL_CODE_DSN", "").strip()


def _lookup_snapshot(library_id: str) -> str | None:
    dsn = _code_dsn()
    if not dsn:
        raise RuntimeError("SCIPAL_CODE_READ_DSN is not configured")
    with psycopg.connect(dsn, connect_timeout=10) as conn:
        row = conn.execute(
            "SELECT snapshot_id FROM code_rag.code_snapshots "
            "WHERE library_id=%s ORDER BY created_at DESC LIMIT 1",
            (library_id,),
        ).fetchone()
        return row[0] if row else None


def bind_link(
    paper_id: str,
    link_id: str,
    *,
    library_id: str,
    snapshot_id: str = "",
) -> dict[str, Any]:
    library_id = (library_id or "").strip()
    if not library_id.startswith("lib_"):
        raise ValueError("library_id must start with lib_")
    pg = corpus_connection()
    try:
        link = pg.execute(
            "SELECT link_id,paper_id,url FROM paper_code_links WHERE paper_id=%s AND link_id=%s",
            (paper_id, link_id),
        ).fetchone()
    finally:
        pg.close()
    if not link:
        raise KeyError("link not found")
    resolved_snapshot = snapshot_id.strip() or _lookup_snapshot(library_id)
    if not resolved_snapshot:
        raise LookupError(f"code library not found: {library_id}")
    binding = {
        "binding_id": _binding_id(paper_id, link_id),
        "paper_id": paper_id,
        "link_id": link_id,
        "library_id": library_id,
        "snapshot_id": resolved_snapshot,
        "status": "bound",
        "parser_supported": False,
        "reason": "language/parser support not recorded at bind time",
    }
    pg = owner_connection()
    try:
        pg.execute(
            """
            INSERT INTO paper_code_libraries
              (binding_id,paper_id,link_id,library_id,snapshot_id,status,parser_supported,reason)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (paper_id,link_id) DO UPDATE SET
              library_id=EXCLUDED.library_id,
              snapshot_id=EXCLUDED.snapshot_id,
              status=EXCLUDED.status,
              parser_supported=EXCLUDED.parser_supported,
              reason=EXCLUDED.reason
            """,
            (
                binding["binding_id"],
                paper_id,
                link_id,
                library_id,
                resolved_snapshot,
                binding["status"],
                binding["parser_supported"],
                binding["reason"],
            ),
        )
        pg.commit()
    finally:
        pg.close()
    return binding


def list_bindings(paper_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            "SELECT binding_id,paper_id,link_id,library_id,snapshot_id,status,"
            "parser_supported,reason,created_at FROM paper_code_libraries "
            "WHERE paper_id=%s ORDER BY created_at",
            (paper_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
