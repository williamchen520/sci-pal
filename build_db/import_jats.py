"""Import JATS XML into the structured schema (no bbox, authoritative xrefs).

Usage:
    python -m build_db.import_jats --file documents_xml/PMC11649735.xml
    python -m build_db.import_jats --dir documents_xml --limit 10

For each paper it replaces the previous XML import and writes:

* sections       — real <sec> parent/child tree
* paragraphs     — section_path + section_id
* citations      — <ref-list> entries with DOI when present
* figures/tables — <fig>/<table-wrap> records
* sentences      — split from paragraph text, no bbox
* sentence_links — <xref> mapped to citation/figure/table (source=jats, 1.0)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from build_db.jats_parser import parse_file
from build_db.sentence_geometry import split_sentences

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "documents_xml"


def _paper_id_for(xml_path: Path, conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT paper_id FROM papers WHERE filename = ?", (xml_path.name,)
    ).fetchone()
    if row:
        return row[0]
    digest = hashlib.md5(xml_path.read_bytes()).hexdigest()[:8]
    return f"paper_{xml_path.stem}_{digest}_xml"


def _clear_paper(conn: sqlite3.Connection, paper_id: str) -> None:
    for table in (
        "sentences",
        "sentence_links",
        "citations",
        "figures",
        "tables",
        "sections",
        "citation_mentions",
    ):
        conn.execute(f"DELETE FROM {table} WHERE paper_id = ?", (paper_id,))
    conn.execute("DELETE FROM paper_links WHERE source_paper_id = ?", (paper_id,))

    # paragraphs_ad deletes from FTS by para_id, which has no index: one full
    # FTS scan per row (12 rows ~ 6 s). Drop it, delete in bulk, clean FTS once.
    trigger = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='paragraphs_ad'"
    ).fetchone()
    if trigger:
        conn.execute("DROP TRIGGER paragraphs_ad")
    conn.execute("DELETE FROM paragraphs WHERE paper_id = ?", (paper_id,))
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paragraphs_fts'"
    ).fetchone()
    if has_fts:
        conn.execute("DELETE FROM paragraphs_fts WHERE paper_id = ?", (paper_id,))
    if trigger:
        conn.execute(trigger[0])


def import_file(
    conn: sqlite3.Connection, xml_path: Path, paper_id: str | None = None
) -> Dict[str, int]:
    data = parse_file(xml_path)
    paper_id = paper_id or _paper_id_for(xml_path, conn)
    if not paper_id:
        return {}

    meta = data.get("metadata") or {}
    _clear_paper(conn, paper_id)

    paragraphs = data.get("paragraphs") or []
    citations = data.get("references") or []
    figures = data.get("figures") or []
    tables = data.get("tables") or []
    sections = data.get("sections") or []

    conn.execute(
        "INSERT OR REPLACE INTO papers "
        "(paper_id, filename, title, authors, abstract, journal, year, doi, keywords, "
        " parse_status, parse_engine, total_paragraphs, total_figures, total_tables, "
        " total_citations, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'xml', ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (
            paper_id,
            xml_path.name,
            meta.get("title") or xml_path.stem,
            "; ".join(meta.get("authors") or []),
            meta.get("abstract") or "",
            meta.get("journal") or "",
            meta.get("year"),
            meta.get("doi") or "",
            ", ".join(meta.get("keywords") or []),
            len(paragraphs),
            len(figures),
            len(tables),
            len(citations),
        ),
    )

    # sections
    section_map: Dict[str, str] = {}
    for index, section in enumerate(sections, 1):
        section_id = f"{paper_id}_sec_{index:04d}"
        section_map[section["section_id"]] = section_id
        conn.execute(
            "INSERT INTO sections "
            "(section_id, paper_id, parent_id, level, title, seq, source) "
            "VALUES (?, ?, ?, ?, ?, ?, 'jats')",
            (
                section_id,
                paper_id,
                section_map.get(section.get("parent_id") or ""),
                section["level"],
                section["title"],
                index,
            ),
        )

    # figures / tables / citations maps (original JATS id -> DB id)
    fig_map: Dict[str, str] = {}
    for index, fig in enumerate(figures, 1):
        fig_id = f"fig_{paper_id}_{index:04d}"
        if fig.get("id"):
            fig_map[fig["id"]] = fig_id
        conn.execute(
            "INSERT INTO figures "
            "(fig_id, paper_id, fig_number, caption, file_path, page, bbox) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL)",
            (
                fig_id,
                paper_id,
                fig.get("label") or f"Fig {index}",
                fig.get("caption") or "",
                fig.get("graphic") or None,
            ),
        )
    table_map: Dict[str, str] = {}
    for index, table in enumerate(tables, 1):
        table_id = f"table_{paper_id}_{index:04d}"
        if table.get("id"):
            table_map[table["id"]] = table_id
        conn.execute(
            "INSERT INTO tables (table_id, paper_id, table_number, caption, markdown) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                table_id,
                paper_id,
                table.get("label") or f"Table {index}",
                table.get("caption") or "",
                table.get("markdown") or "",
            ),
        )
    citation_map: Dict[str, str] = {}
    for index, ref in enumerate(citations, 1):
        citation_id = f"cite_{paper_id}_{index:04d}"
        if ref.get("id"):
            citation_map[ref["id"]] = citation_id
        conn.execute(
            "INSERT INTO citations "
            "(citation_id, paper_id, ref_number, raw_text, doi, title, authors, journal, year) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)",
            (
                citation_id,
                paper_id,
                ref.get("id") or str(index),
                ref.get("text") or "",
                ref.get("doi"),
                ref.get("title") or "",
                ref.get("year"),
            ),
        )

    # paragraphs + sentences + xref links
    stats = {
        "sections": len(sections),
        "paragraphs": 0,
        "sentences": 0,
        "citations": len(citations),
        "figures": len(figures),
        "tables": len(tables),
        "links": 0,
    }
    for index, para in enumerate(paragraphs):
        para_id = f"{paper_id}_para_{index:05d}"
        section_id = section_map.get(para.get("section_id") or "")
        path = para.get("path") or []
        conn.execute(
            "INSERT INTO paragraphs "
            "(para_id, paper_id, section_level1, section_level2, section_level3, "
            " text, sequence, page, bbox, section_path, section_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)",
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
        if not sentences:
            continue
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
            conn.execute(
                "INSERT INTO sentences "
                "(sentence_id, para_id, paper_id, text, sequence, page, bbox, section_id, "
                " char_start, char_end) "
                "VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)",
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
            conn.execute(
                "INSERT OR REPLACE INTO sentence_links "
                "(link_id, sentence_id, para_id, paper_id, source_type, target_type, "
                " target_id, relation, page, bbox, source, confidence) "
                "VALUES (?, ?, ?, ?, 'sentence', ?, ?, ?, NULL, NULL, 'jats', 1.0)",
                (
                    f"jats_{sentence_id}_{target_type}_{target_id}",
                    sentence_id,
                    para_id,
                    paper_id,
                    target_type,
                    target_id,
                    "cites" if target_type == "citation" else "mentions",
                ),
            )
            stats["links"] += 1

    return stats


def import_dir(
    db_path: Path | str = DEFAULT_DB,
    directory: Path | str = DEFAULT_DIR,
    limit: int = 0,
    resume: bool = False,
) -> Dict[str, int]:
    directory = Path(directory)
    files = sorted(directory.glob("*.xml"))
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    conn.execute("PRAGMA synchronous=NORMAL")
    total = {"papers": 0, "sections": 0, "paragraphs": 0, "sentences": 0, "links": 0}
    try:
        for index, xml_path in enumerate(files, 1):
            if resume:
                row = conn.execute(
                    "SELECT 1 FROM papers p JOIN sections s ON s.paper_id = p.paper_id "
                    "WHERE p.filename = ? AND s.source = 'jats' LIMIT 1",
                    (xml_path.name,),
                ).fetchone()
                if row:
                    continue
            try:
                stats = import_file(conn, xml_path)
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"FAILED {xml_path.name}: {str(exc)[:120]}", flush=True)
                continue
            if not stats:
                continue
            total["papers"] += 1
            for key in ("sections", "paragraphs", "sentences", "links"):
                total[key] += stats.get(key, 0)
            if total["papers"] % 100 == 0:
                print(f"progress {total} at {xml_path.name}", flush=True)
            if limit and total["papers"] >= limit:
                break
    finally:
        conn.close()
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--file")
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.file:
        conn = sqlite3.connect(args.db)
        print(import_file(conn, Path(args.file)))
        conn.commit()
        conn.close()
    else:
        print(import_dir(args.db, args.dir, args.limit))
