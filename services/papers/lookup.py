"""Paper lookup by filename (PostgreSQL only)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.db.pg_pool import main_read_connection


def find_parsed_paper(filename: str) -> Optional[Dict[str, Any]]:
    if not filename:
        return None
    pg = main_read_connection()
    try:
        row = pg.execute(
            "SELECT paper_id, filename, title, authors, year, total_paragraphs "
            "FROM papers WHERE filename = %s "
            "ORDER BY total_paragraphs DESC NULLS LAST, created_at ASC LIMIT 1",
            (filename,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()
