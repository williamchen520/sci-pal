"""Import JATS XML directly into the production PostgreSQL schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from build_db.jats_parser import parse_file
from build_db.sentence_geometry import split_sentences
from services.db.pg_pool import pg_connection
from services.papers import pg_writes


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _find_paper_id(pg, filename: str) -> str | None:
    row = pg.execute(
        "SELECT paper_id FROM papers WHERE filename=%s LIMIT 1", (filename,)
    ).fetchone()
    return row[0] if row else None


def _clear_graph(pg, paper_id: str) -> None:
    pg.execute("DELETE FROM sentence_links WHERE paper_id=%s", (paper_id,))
    pg.execute("DELETE FROM sentences WHERE paper_id=%s", (paper_id,))
    pg.execute("DELETE FROM paragraphs WHERE paper_id=%s", (paper_id,))
    pg.execute("DELETE FROM sections WHERE paper_id=%s", (paper_id,))
    pg.execute("DELETE FROM figures WHERE paper_id=%s", (paper_id,))
    pg.execute('DELETE FROM "tables" WHERE paper_id=%s', (paper_id,))
    pg.execute("DELETE FROM citations WHERE paper_id=%s", (paper_id,))


def import_file(xml_path: Path, paper_id: str | None = None) -> Dict[str, int]:
    data = parse_file(xml_path)
    meta = data.get("metadata") or {}
    paragraphs = data.get("paragraphs") or []
    citations = data.get("references") or []
    figures = data.get("figures") or []
    tables = data.get("tables") or []
    sections = data.get("sections") or []
    stats = {
        "sections": len(sections),
        "paragraphs": 0,
        "sentences": 0,
        "citations": len(citations),
        "figures": len(figures),
        "tables": len(tables),
        "links": 0,
    }
    pg = pg_connection()
    try:
        paper_id = paper_id or _find_paper_id(pg, xml_path.name)
        if not paper_id:
            return {}
        _clear_graph(pg, paper_id)
        pg_writes._upsert_paper_row(
            pg,
            {
                "paper_id": paper_id,
                "filename": xml_path.name,
                "title": meta.get("title") or xml_path.stem,
                "authors": "; ".join(meta.get("authors") or []),
                "abstract": meta.get("abstract") or "",
                "journal": meta.get("journal") or "",
                "year": _int_or_none(meta.get("year")),
                "doi": meta.get("doi") or "",
                "keywords": ", ".join(meta.get("keywords") or []),
                "parse_status": "completed",
                "parse_engine": "xml",
                "total_paragraphs": len(paragraphs),
                "total_figures": len(figures),
                "total_tables": len(tables),
                "total_citations": len(citations),
            },
        )

        section_map: Dict[str, str] = {}
        for index, section in enumerate(sections, 1):
            section_id = f"{paper_id}_sec_{index:04d}"
            section_map[section["section_id"]] = section_id
            pg.execute(
                "INSERT INTO sections (section_id,paper_id,parent_id,level,title,seq,source) "
                "VALUES (%s,%s,%s,%s,%s,%s,'jats')",
                (
                    section_id,
                    paper_id,
                    section_map.get(section.get("parent_id") or ""),
                    section["level"],
                    section["title"],
                    index,
                ),
            )

        fig_map: Dict[str, str] = {}
        for index, fig in enumerate(figures, 1):
            fig_id = f"fig_{paper_id}_{index:04d}"
            if fig.get("id"):
                fig_map[fig["id"]] = fig_id
            pg.execute(
                "INSERT INTO figures (fig_id,paper_id,fig_number,caption,file_path) "
                "VALUES (%s,%s,%s,%s,%s)",
                (fig_id, paper_id, fig.get("label"), fig.get("caption"), None),
            )

        table_map: Dict[str, str] = {}
        for index, table in enumerate(tables, 1):
            table_id = f"tbl_{paper_id}_{index:04d}"
            if table.get("id"):
                table_map[table["id"]] = table_id
            pg.execute(
                'INSERT INTO "tables" (table_id,paper_id,table_number,caption,markdown) '
                "VALUES (%s,%s,%s,%s,%s)",
                (table_id, paper_id, table.get("label"), table.get("caption"), table.get("markdown")),
            )

        citation_map: Dict[str, str] = {}
        for index, ref in enumerate(citations, 1):
            citation_id = f"cite_{paper_id}_{index:04d}"
            if ref.get("id"):
                citation_map[ref["id"]] = citation_id
            pg.execute(
                "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text,doi,title,authors,journal,year) "
                "VALUES (%s,%s,%s,%s,%s,%s,NULL,NULL,%s)",
                (
                    citation_id,
                    paper_id,
                    ref.get("id") or str(index),
                    ref.get("text") or "",
                    ref.get("doi"),
                    ref.get("title") or "",
                    _int_or_none(ref.get("year")),
                ),
            )

        for index, para in enumerate(paragraphs):
            para_id = f"{paper_id}_para_{index:05d}"
            section_id = section_map.get(para.get("section_id") or "")
            path = para.get("path") or []
            pg.execute(
                "INSERT INTO paragraphs (para_id,paper_id,section_level1,section_level2,"
                "section_level3,text,sequence,section_path,section_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    para_id,
                    paper_id,
                    path[0] if len(path) > 0 else None,
                    path[1] if len(path) > 1 else None,
                    path[2] if len(path) > 2 else None,
                    para["text"],
                    para["sequence"],
                    json.dumps(path, ensure_ascii=False) if path else None,
                    section_id,
                ),
            )
            stats["paragraphs"] += 1
            sentences = split_sentences(para["text"])
            offsets = []
            cursor = 0
            for sentence in sentences:
                start = para["text"].find(sentence, cursor)
                if start < 0:
                    start = cursor
                offsets.append((start, start + len(sentence)))
                cursor = start + len(sentence)
            for sindex, sentence in enumerate(sentences, 1):
                sentence_id = f"{para_id}_sent_{sindex:03d}"
                pg.execute(
                    "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,"
                    "section_id,char_start,char_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        sentence_id,
                        para_id,
                        paper_id,
                        sentence,
                        sindex,
                        section_id,
                        offsets[sindex - 1][0],
                        offsets[sindex - 1][1],
                    ),
                )
                stats["sentences"] += 1
            linked = set()
            for xref in para.get("xrefs") or []:
                offset = xref.get("offset", 0)
                sentence_index = None
                for sindex, (start, end) in enumerate(offsets):
                    if start <= offset <= end:
                        sentence_index = sindex + 1
                        break
                if sentence_index is None:
                    continue
                sentence_id = f"{para_id}_sent_{sentence_index:03d}"
                rid = xref.get("rid") or ""
                ref_type = (xref.get("ref_type") or "").lower()
                if ref_type == "bibr" and rid in citation_map:
                    target_type, target_id = "citation", citation_map[rid]
                elif ref_type == "fig" and rid in fig_map:
                    target_type, target_id = "figure", fig_map[rid]
                elif ref_type == "table" and rid in table_map:
                    target_type, target_id = "table", table_map[rid]
                else:
                    continue
                key = (sentence_id, target_type, target_id)
                if key in linked:
                    continue
                linked.add(key)
                pg.execute(
                    "INSERT INTO sentence_links (link_id,sentence_id,para_id,paper_id,"
                    "source_type,target_type,target_id,relation,source,confidence) "
                    "VALUES (%s,%s,%s,%s,'sentence',%s,%s,'mentions','jats-regex',0.6)",
                    (
                        f"jats_{sentence_id}_{target_type}_{target_id}",
                        sentence_id,
                        para_id,
                        paper_id,
                        target_type,
                        target_id,
                    ),
                )
                stats["links"] += 1
        pg.commit()
        return stats
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
