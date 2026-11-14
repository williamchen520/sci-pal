"""Read-only native HTML source metadata."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection


def html_native(paper_id: str, *, include_paragraphs: bool = False) -> dict[str, Any] | None:
    pg = corpus_connection()
    try:
        article = pg.execute(
            "SELECT source_id,paper_id,source_url,content_hash,title,doi,journal,"
            "published,license,native_json FROM html_articles WHERE paper_id=%s LIMIT 1",
            (paper_id,),
        ).fetchone()
        if not article:
            return None
        source_id = article["source_id"]
        para_total = pg.execute(
            "SELECT count(*) AS count FROM html_paragraphs WHERE source_id=%s", (source_id,)
        ).fetchone()["count"]
        sections = [
            dict(row)
            for row in pg.execute(
                "SELECT native_section_id,title,section_order FROM html_sections "
                "WHERE source_id=%s ORDER BY section_order",
                (source_id,),
            ).fetchall()
        ]
        if include_paragraphs:
            paragraphs = [
                dict(row)
                for row in pg.execute(
                    "SELECT native_para_id,section_id,text,para_order FROM html_paragraphs "
                    "WHERE source_id=%s ORDER BY section_id, para_order",
                    (source_id,),
                ).fetchall()
            ]
            by_section: dict[str, list[dict[str, Any]]] = {}
            for row in paragraphs:
                by_section.setdefault(row["section_id"], []).append(row)
            for section in sections:
                section["paragraphs"] = by_section.get(section["native_section_id"], [])
        return {
            "paper_id": paper_id,
            "source_id": source_id,
            "source_url": article.get("source_url") or "",
            "content_hash": article.get("content_hash") or "",
            "title": article.get("title") or "",
            "doi": article.get("doi") or "",
            "journal": article.get("journal") or "",
            "published": article.get("published") or "",
            "license": article.get("license") or "",
            "native": article.get("native_json") or {},
            "sections": sections,
            "section_count": len(sections),
            "paragraph_count": int(para_total),
        }
    finally:
        pg.close()
