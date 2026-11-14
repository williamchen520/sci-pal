"""Read-only native PDF metadata."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection


def pdf_native(paper_id: str, *, include_paragraphs: bool = False) -> dict[str, Any] | None:
    pg = corpus_connection()
    try:
        doc = pg.execute(
            "SELECT source_id,paper_id,source_uri,content_hash,parser,page_count,native_json "
            "FROM pdf_documents WHERE paper_id=%s LIMIT 1",
            (paper_id,),
        ).fetchone()
        if not doc:
            return None
        source_id = doc["source_id"]
        total = pg.execute(
            "SELECT count(*) AS count FROM pdf_paragraphs WHERE source_id=%s",
            (source_id,),
        ).fetchone()["count"]
        result: dict[str, Any] = {
            "paper_id": paper_id,
            "source_id": source_id,
            "source_uri": doc.get("source_uri") or "",
            "content_hash": doc.get("content_hash") or "",
            "parser": doc.get("parser") or "",
            "page_count": int(doc.get("page_count") or 0),
            "paragraph_count": int(total),
            "native": doc.get("native_json") or {},
        }
        if include_paragraphs:
            result["paragraphs"] = [
                dict(row)
                for row in pg.execute(
                    "SELECT native_para_id,para_id,page,bbox,text,para_order "
                    "FROM pdf_paragraphs WHERE source_id=%s ORDER BY para_order",
                    (source_id,),
                ).fetchall()
            ]
        return result
    finally:
        pg.close()
