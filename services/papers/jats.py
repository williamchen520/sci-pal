"""Read-only JATS native metadata."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection


def jats_native(paper_id: str) -> dict[str, Any] | None:
    pg = corpus_connection()
    try:
        article = pg.execute(
            "SELECT source_id,paper_id,article_type,journal_title,article_title,"
            "license,native_json FROM jats_articles WHERE paper_id=%s LIMIT 1",
            (paper_id,),
        ).fetchone()
        if not article:
            return None
        sections = pg.execute(
            "SELECT native_section_id,sec_type,title,depth,section_path,section_order "
            "FROM jats_sections WHERE source_id=%s ORDER BY section_order",
            (article.get("source_id"),),
        ).fetchall()
        return {
            "paper_id": paper_id,
            "source_id": article.get("source_id"),
            "article_type": article.get("article_type") or "",
            "journal_title": article.get("journal_title") or "",
            "article_title": article.get("article_title") or "",
            "license": article.get("license") or "",
            "sections": [dict(row) for row in sections],
        }
    finally:
        pg.close()
