"""Import JATS fulltext into the production PG schema (P3b1)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from build_db.jats_parser import parse_file
from services.papers import pg_writes


def _adapt(parsed: Dict[str, Any], paper_id: str, filename: str) -> Dict[str, Any]:
    meta = parsed.get("metadata") or {}
    paragraphs = []
    for index, para in enumerate(parsed.get("paragraphs") or []):
        text = para.get("text") or ""
        if not text:
            continue
        path = para.get("path") or []
        paragraphs.append(
            {
                "para_id": f"{paper_id}_para_{index:05d}",
                "paper_id": paper_id,
                "section_type": path[0] if path else "",
                "section_title": path[-1] if path else "",
                "text_content": text,
                "para_index": para.get("sequence") or index,
                "page_number": None,
                "bbox": None,
                "section_path": path,
            }
        )
    return {
        "paper_id": paper_id,
        "metadata": {
            "file_name": filename,
            "title": meta.get("title"),
            "authors": meta.get("authors") or [],
            "abstract": meta.get("abstract") or "",
            "journal": meta.get("journal") or "",
            "year": meta.get("year"),
            "doi": meta.get("doi") or "",
            "keywords": meta.get("keywords") or [],
            "parse_engine": "jats",
        },
        "paragraphs": paragraphs,
        "figures": [],
        "tables": [],
        "citations": [],
        "intext_citations": [],
    }


def import_jats(xml_path: Path, paper_id: str, abstract_paper_id: str | None = None) -> str:
    parsed = parse_file(xml_path)
    payload = _adapt(parsed, paper_id, Path(xml_path).name)
    if not pg_writes.write_parsed_paper(payload):
        raise RuntimeError("PG fulltext write failed")
    if abstract_paper_id and abstract_paper_id != paper_id:
        from services.db.pg_pool import pg_connection

        pg = pg_connection()
        try:
            pg.execute("DELETE FROM papers WHERE paper_id = %s", (abstract_paper_id,))
            pg.commit()
        finally:
            pg.close()
    return paper_id
