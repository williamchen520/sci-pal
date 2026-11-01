#!/usr/bin/env python3
"""P3: import PDF-parsed rows and layout into scipal_v2.

Structure rows come from the existing SQLite PDF parse (page/bbox preserved).
pdf_pages/pdf_blocks are rebuilt from the source PDF with PyMuPDF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_SQLITE = ROOT / "data" / "research.db"
DEFAULT_PDF_DIR = ROOT / "documents"


def _clean(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_rows(sqlite_path: Path) -> List[Dict]:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT paper_id, filename, workspace_id, title, authors, abstract, "
                "journal, year, doi FROM papers WHERE filename LIKE '%.pdf'"
            )
        ]
    finally:
        conn.close()


def _sqlite_rows(conn: sqlite3.Connection, table: str, paper_id: str) -> List[Dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(
        f'SELECT * FROM "{table}" WHERE paper_id=?', (paper_id,)
    )]


def _section_for_page(conn, paper_id: str, page: int | None):
    if page is None:
        return None
    row = conn.execute(
        "SELECT section_id FROM sections WHERE paper_id=%s AND page IS NOT NULL "
        "AND page <= %s ORDER BY page DESC, seq DESC LIMIT 1",
        (paper_id, page),
    ).fetchone()
    return row[0] if row else None


def import_one(conn, paper: Dict, pdf_path: Path | None, old: sqlite3.Connection) -> Dict:
    import pymupdf as fitz

    paper_id = paper["paper_id"]
    document_id = f"doc_{paper_id}_pdf"
    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute("DELETE FROM papers WHERE paper_id=%s", (paper_id,))
    conn.execute(
        """INSERT INTO papers
           (paper_id, workspace_id, title, authors, journal, year, doi, abstract,
            parse_status, fulltext_status, source_flags)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'completed','fulltext',%s)""",
        (
            paper_id,
            paper.get("workspace_id") or "ws_default",
            _clean(paper.get("title") or ""),
            _clean(paper.get("authors") or ""),
            paper.get("journal") or "",
            paper.get("year"),
            paper.get("doi") or "",
            _clean(paper.get("abstract") or ""),
            json.dumps(
                {
                    "has_xml": False,
                    "has_pdf": pdf_path is not None,
                    "coordinate_source": "pdf" if pdf_path else "unavailable",
                }
            ),
        ),
    )
    sha = _sha256(pdf_path) if pdf_path else "missing"
    conn.execute(
        """INSERT INTO documents
           (document_id, paper_id, source_type, source_path, sha256, parser, parser_version)
           VALUES (%s,%s,'pdf',%s,%s,'pdf-layout','v2')""",
        (
            document_id,
            paper_id,
            f"documents/{pdf_path.name}" if pdf_path else "",
            sha,
        ),
    )
    root_node = f"node_{paper_id}_root"
    conn.execute(
        """INSERT INTO source_nodes
           (node_id, document_id, paper_id, node_type, source_path, native_json)
           VALUES (%s,%s,%s,'paper','/pdf',%s)""",
        (root_node, document_id, paper_id, json.dumps({"tag": "pdf"})),
    )

    sections = _sqlite_rows(old, "sections", paper_id)
    section_map: Dict[str, str] = {}
    section_nodes: Dict[str, str] = {}
    for index, section in enumerate(sections, 1):
        sid = f"sec_{paper_id}_{index:04d}"
        section_map[section["section_id"]] = sid
        node_id = f"node_{paper_id}_sec_{index:04d}"
        section_nodes[section["section_id"]] = node_id
        parent = section_map.get(section.get("parent_id") or "")
        page = section.get("page")
        bbox = section.get("bbox")
        conn.execute(
            """INSERT INTO sections
               (section_id, paper_id, parent_id, level, seq, title, path, depth,
                source_node_id, source_type, page, bbox, coordinate_source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pdf',%s,%s,%s)""",
            (
                sid, paper_id, parent, section.get("level") or 1, index,
                _clean(section.get("title") or ""), section.get("path") or "",
                section.get("depth"), node_id, page, bbox,
                "pdf" if page is not None or bbox else "unavailable",
            ),
        )
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type,
                source_path, source_order, native_json)
               VALUES (%s,%s,%s,%s,'section',%s,%s,%s)""",
            (
                node_id, document_id, paper_id,
                section_nodes.get(section.get("parent_id") or "") or root_node,
                f"/sections/{index}", index,
                json.dumps({"tag": "section", "title": _clean(section.get("title") or "")}, ensure_ascii=False),
            ),
        )

    para_map: Dict[str, str] = {}
    para_nodes: Dict[str, str] = {}
    for index, para in enumerate(_sqlite_rows(old, "paragraphs", paper_id), 1):
        pid = f"para_{paper_id}_{index:05d}"
        para_map[para["para_id"]] = pid
        sid = section_map.get(para.get("section_id") or "")
        node_id = f"node_{paper_id}_para_{index:05d}"
        para_nodes[para["para_id"]] = node_id
        page, bbox = para.get("page"), para.get("bbox")
        conn.execute(
            """INSERT INTO paragraphs
               (para_id, paper_id, section_id, seq, text, source_node_id, source_type,
                page, bbox, coordinate_source)
               VALUES (%s,%s,%s,%s,%s,%s,'pdf',%s,%s,%s)""",
            (
                pid, paper_id, sid, para.get("sequence") or index - 1,
                _clean(para.get("text") or ""), node_id, page, bbox,
                "pdf" if page is not None or bbox else "unavailable",
            ),
        )
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type,
                source_path, source_order, native_json)
               VALUES (%s,%s,%s,%s,'paragraph',%s,%s,%s)""",
            (
                node_id, document_id, paper_id,
                section_nodes.get(para.get("section_id") or "") or root_node,
                f"/paragraphs/{index}", index,
                json.dumps({"tag": "paragraph", "page": page, "bbox": bbox}),
            ),
        )

    for index, sent in enumerate(_sqlite_rows(old, "sentences", paper_id), 1):
        para_id = para_map.get(sent.get("para_id") or "")
        if not para_id:
            continue
        sid = section_map.get(sent.get("section_id") or "")
        page, bbox = sent.get("page"), sent.get("bbox")
        conn.execute(
            """INSERT INTO sentences
               (sentence_id, paper_id, para_id, section_id, seq, text,
                source_node_id, source_type, page, bbox, coordinate_source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'pdf',%s,%s,%s)""",
            (
                f"sent_{paper_id}_{index:06d}", paper_id, para_id, sid,
                sent.get("sequence") or index - 1, _clean(sent.get("text") or ""),
                para_nodes.get(sent.get("para_id") or ""), page, bbox,
                "pdf" if page is not None or bbox else "unavailable",
            ),
        )

    fig_count = table_count = 0
    for index, fig in enumerate(_sqlite_rows(old, "figures", paper_id), 1):
        page, bbox = fig.get("page"), fig.get("bbox")
        sid = _section_for_page(conn, paper_id, page)
        conn.execute(
            """INSERT INTO figures
               (fig_id, paper_id, section_id, para_id, fig_number, caption, file_path,
                source_type, page, bbox, placement_source, coordinate_source)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,'pdf',%s,%s,%s,%s)""",
            (
                f"fig_{paper_id}_{index:04d}", paper_id, sid,
                fig.get("fig_number") or "", _clean(fig.get("caption") or ""),
                fig.get("file_path") or None, page, bbox,
                "pdf-region" if sid else "unresolved",
                "pdf" if page is not None or bbox else "unavailable",
            ),
        )
        fig_count += 1
    for index, table in enumerate(_sqlite_rows(old, "tables", paper_id), 1):
        page, bbox = table.get("page"), table.get("bbox")
        sid = _section_for_page(conn, paper_id, page)
        conn.execute(
            """INSERT INTO "tables"
               (table_id, paper_id, section_id, para_id, table_number, caption, markdown,
                source_type, page, bbox, placement_source, coordinate_source)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,'pdf',%s,%s,%s,%s)""",
            (
                f"table_{paper_id}_{index:04d}", paper_id, sid,
                table.get("table_number") or "", _clean(table.get("caption") or ""),
                _clean(table.get("markdown") or ""), page, bbox,
                "pdf-region" if sid else "unresolved",
                "pdf" if page is not None or bbox else "unavailable",
            ),
        )
        table_count += 1

    pages = blocks = 0
    if pdf_path and pdf_path.exists():
        with fitz.open(pdf_path) as doc:
            for page_no, page in enumerate(doc, 1):
                page_node = f"node_{paper_id}_page_{page_no:04d}"
                conn.execute(
                    """INSERT INTO source_nodes
                       (node_id, document_id, paper_id, parent_node_id, node_type,
                        source_path, source_order, native_json)
                       VALUES (%s,%s,%s,%s,'page',%s,%s,%s)""",
                    (
                        page_node, document_id, paper_id, root_node,
                        f"/pages/{page_no}", page_no,
                        json.dumps({"page": page_no, "width": page.rect.width, "height": page.rect.height}),
                    ),
                )
                conn.execute(
                    """INSERT INTO pdf_pages
                       (document_id, paper_id, page_no, width, height, text, layout_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        document_id, paper_id, page_no, page.rect.width, page.rect.height,
                        _clean(page.get_text("text")),
                        json.dumps({"blocks": len(page.get_text("blocks"))}),
                    ),
                )
                for block_index, block in enumerate(page.get_text("blocks"), 1):
                    x0, y0, x1, y1, text, _no, block_type = block[:7]
                    conn.execute(
                        """INSERT INTO pdf_blocks
                           (block_id, document_id, paper_id, page_no, bbox, block_type,
                            text, source_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            f"block_{paper_id}_{page_no:04d}_{block_index:04d}",
                            document_id, paper_id, page_no,
                            f"{x0:.2f},{y0:.2f},{x1:.2f},{y1:.2f}",
                            str(block_type), _clean((text or "").strip()), block_index,
                        ),
                    )
                    blocks += 1
                pages += 1
    return {
        "sections": len(sections), "paragraphs": len(para_map),
        "sentences": len(_sqlite_rows(old, "sentences", paper_id)),
        "figures": fig_count, "tables": table_count,
        "pages": pages, "blocks": blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--sqlite-db", default=str(DEFAULT_SQLITE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--paper-id", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to write a non-scipal_v2 database")

    import psycopg

    papers = _source_rows(Path(args.sqlite_db))
    old = sqlite3.connect(f"file:{args.sqlite_db}?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    files: List = []
    for paper in papers:
        if args.paper_id and paper["paper_id"] != args.paper_id:
            continue
        path = Path(args.pdf_dir) / paper["filename"]
        files.append((paper, path if path.exists() else None))
        if args.limit and len(files) >= args.limit:
            break
    totals = {key: 0 for key in ("papers", "sections", "paragraphs", "sentences", "figures", "tables", "pages", "blocks")}
    failures = []
    with psycopg.connect(args.pg_dsn) as conn:
        for paper, path in files:
            try:
                stats = import_one(conn, paper, path, old)
                conn.commit()
                totals["papers"] += 1
                for key, value in stats.items():
                    totals[key] += value
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                failures.append({"paper_id": paper["paper_id"], "error": str(exc)[:300]})
    old.close()
    print(json.dumps({"totals": totals, "attempted": len(files), "failure_count": len(failures), "failures": failures[:10]}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
