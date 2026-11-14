"""Read-only paper source provenance."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection


def list_sources(paper_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            "SELECT source_id,paper_id,source_kind,source_uri,content_hash,"
            "parser,parser_version,is_primary,retrieved_at,metadata,created_at "
            "FROM paper_sources WHERE paper_id=%s ORDER BY is_primary DESC, source_kind",
            (paper_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
