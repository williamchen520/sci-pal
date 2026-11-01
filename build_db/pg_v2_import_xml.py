#!/usr/bin/env python3
"""P2: import JATS XML into scipal_v2 (source-aware schema).

XML keeps source_nodes/XPath; page/bbox stay NULL with
coordinate_source='xml-unavailable'. No PDF rows are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_db.jats_parser import parse_file  # noqa: E402
from build_db.sentence_geometry import split_sentences  # noqa: E402

DEFAULT_SQLITE = ROOT / "data" / "research.db"
DEFAULT_XML_DIR = ROOT / "documents_xml"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _paper_map(sqlite_path: Path) -> Dict[str, Dict[str, Any]]:
    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT paper_id, filename, workspace_id FROM papers "
            "WHERE parse_engine='xml' AND filename IS NOT NULL"
        ).fetchall()
        return {row["filename"]: dict(row) for row in rows}
    finally:
        conn.close()


def import_one(conn, xml_path: Path, meta: Dict[str, Any]) -> Dict[str, int]:
    data = parse_file(xml_path)
    paper_id = meta["paper_id"]
    workspace_id = meta.get("workspace_id") or "ws_default"
    paper_meta = data.get("metadata") or {}
    document_id = f"doc_{paper_id}_xml"
    sha = _sha256(xml_path)
    source_rel = f"documents_xml/{xml_path.name}"

    conn.execute("SET CONSTRAINTS ALL DEFERRED")
    conn.execute("DELETE FROM papers WHERE paper_id=%s", (paper_id,))
    conn.execute(
        """INSERT INTO papers
           (paper_id, workspace_id, title, authors, journal, year, doi, abstract,
            parse_status, source_flags)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'completed',%s)""",
        (
            paper_id,
            workspace_id,
            paper_meta.get("title") or xml_path.stem,
            "; ".join(paper_meta.get("authors") or []),
            paper_meta.get("journal") or "",
            paper_meta.get("year"),
            paper_meta.get("doi") or "",
            paper_meta.get("abstract") or "",
            json.dumps(
                {
                    "has_xml": True,
                    "has_pdf": False,
                    "coordinate_source": "xml-unavailable",
                }
            ),
        ),
    )
    conn.execute(
        """INSERT INTO documents
           (document_id, paper_id, source_type, source_path, sha256, parser, parser_version)
           VALUES (%s,%s,'xml',%s,%s,'jats-parser','v2')""",
        (document_id, paper_id, source_rel, sha),
    )
    root_node = f"node_{paper_id}_root"
    conn.execute(
        """INSERT INTO source_nodes
           (node_id, document_id, paper_id, parent_node_id, node_type, source_path, native_json)
           VALUES (%s,%s,%s,NULL,'paper','/article',%s)""",
        (root_node, document_id, paper_id, json.dumps({"tag": "article"})),
    )

    section_nodes: Dict[str, str] = {}
    section_ids: Dict[str, str] = {}
    section_parent: Dict[str, str | None] = {}
    for index, section in enumerate(data.get("sections") or [], 1):
        old_id = section["section_id"]
        sid = f"sec_{paper_id}_{index:04d}"
        section_ids[old_id] = sid
        section_parent[old_id] = section.get("parent_id")
        parent_sid = section_ids.get(section.get("parent_id") or "")
        node_id = f"node_{paper_id}_sec_{index:04d}"
        section_nodes[old_id] = node_id
        conn.execute(
            """INSERT INTO sections
               (section_id, paper_id, parent_id, level, seq, title, path, depth,
                source_node_id, source_type, page, bbox, coordinate_source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'xml',NULL,NULL,'xml-unavailable')""",
            (
                sid,
                paper_id,
                parent_sid,
                section.get("level") or 1,
                index,
                section.get("title") or "",
                " / ".join(section.get("path") or []),
                len(section.get("path") or []),
                node_id,
            ),
        )
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type, source_path,
                source_order, native_json)
               VALUES (%s,%s,%s,%s,'section',%s,%s,%s)""",
            (
                node_id,
                document_id,
                paper_id,
                section_nodes.get(section.get("parent_id") or "") or root_node,
                section.get("xpath"),
                index,
                json.dumps(
                    {
                        "tag": "sec",
                        "title": section.get("title") or "",
                        "path": section.get("path") or [],
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    para_nodes: Dict[int, str] = {}
    sentence_count = 0
    for index, para in enumerate(data.get("paragraphs") or [], 1):
        para_id = f"para_{paper_id}_{index:05d}"
        old_section = para.get("section_id")
        sid = section_ids.get(old_section or "")
        para_node = f"node_{paper_id}_para_{index:05d}"
        para_nodes[index - 1] = para_node
        conn.execute(
            """INSERT INTO paragraphs
               (para_id, paper_id, section_id, seq, text, source_node_id, source_type,
                page, bbox, coordinate_source)
               VALUES (%s,%s,%s,%s,%s,%s,'xml',NULL,NULL,'xml-unavailable')""",
            (
                para_id,
                paper_id,
                sid,
                para.get("sequence") or index - 1,
                para.get("text") or "",
                para_node,
            ),
        )
        para_xpath = para.get("xpath") or ""
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type, source_path,
                source_order, native_json)
               VALUES (%s,%s,%s,%s,'paragraph',%s,%s,%s)""",
            (
                para_node,
                document_id,
                paper_id,
                section_nodes.get(old_section or "") or root_node,
                para_xpath,
                index,
                json.dumps(
                    {"tag": "p", "text_length": len(para.get("text") or "")},
                    ensure_ascii=False,
                ),
            ),
        )
        for sent_index, text in enumerate(
            split_sentences(para.get("text") or ""), 1
        ):
            sentence_id = f"{para_id}_sent_{sent_index:03d}"
            sent_node = f"node_{paper_id}_{index:05d}_sent_{sent_index:03d}"
            conn.execute(
                """INSERT INTO sentences
                   (sentence_id, paper_id, para_id, section_id, seq, text,
                    source_node_id, source_type, page, bbox, coordinate_source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'xml',NULL,NULL,'xml-unavailable')""",
                (
                    sentence_id,
                    paper_id,
                    para_id,
                    sid,
                    sent_index - 1,
                    text,
                    sent_node,
                ),
            )
            conn.execute(
                """INSERT INTO source_nodes
                   (node_id, document_id, paper_id, parent_node_id, node_type,
                    source_path, source_order, native_json)
                   VALUES (%s,%s,%s,%s,'sentence',%s,%s,%s)""",
                (
                    sent_node,
                    document_id,
                    paper_id,
                    para_node,
                    f"{para_xpath}#sentence-{sent_index}",
                    sent_index,
                    json.dumps({"tag": "sentence", "text_length": len(text)}),
                ),
            )
            sentence_count += 1

    fig_count = 0
    for index, fig in enumerate(data.get("figures") or [], 1):
        old_section = fig.get("section_id")
        sid = section_ids.get(old_section or "")
        fig_id = f"fig_{paper_id}_{index:04d}"
        fig_node = f"node_{paper_id}_fig_{index:04d}"
        conn.execute(
            """INSERT INTO figures
               (fig_id, paper_id, section_id, para_id, fig_number, caption, file_path,
                source_node_id, source_type, page, bbox, placement_source,
                coordinate_source)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,'xml',NULL,NULL,%s,'xml-unavailable')""",
            (
                fig_id,
                paper_id,
                sid,
                fig.get("label") or "",
                fig.get("caption") or "",
                fig.get("graphic") or None,
                fig_node,
                "jats-parent" if sid else "unresolved",
            ),
        )
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type, source_path,
                source_order, native_json)
               VALUES (%s,%s,%s,%s,'figure',%s,%s,%s)""",
            (
                fig_node,
                document_id,
                paper_id,
                section_nodes.get(old_section or "") or root_node,
                fig.get("xpath") or f"/article/body/fig[{index}]",
                index,
                json.dumps(
                    {"tag": "fig", "id": fig.get("id") or "", "caption": fig.get("caption") or ""},
                    ensure_ascii=False,
                ),
            ),
        )
        fig_count += 1

    table_count = 0
    for index, table in enumerate(data.get("tables") or [], 1):
        old_section = table.get("section_id")
        sid = section_ids.get(old_section or "")
        table_id = f"table_{paper_id}_{index:04d}"
        table_node = f"node_{paper_id}_table_{index:04d}"
        conn.execute(
            """INSERT INTO "tables"
               (table_id, paper_id, section_id, para_id, table_number, caption, markdown,
                source_node_id, source_type, page, bbox, placement_source,
                coordinate_source)
               VALUES (%s,%s,%s,NULL,%s,%s,%s,%s,'xml',NULL,NULL,%s,'xml-unavailable')""",
            (
                table_id,
                paper_id,
                sid,
                table.get("label") or "",
                table.get("caption") or "",
                table.get("markdown") or "",
                table_node,
                "jats-parent" if sid else "unresolved",
            ),
        )
        conn.execute(
            """INSERT INTO source_nodes
               (node_id, document_id, paper_id, parent_node_id, node_type, source_path,
                source_order, native_json)
               VALUES (%s,%s,%s,%s,'table',%s,%s,%s)""",
            (
                table_node,
                document_id,
                paper_id,
                section_nodes.get(old_section or "") or root_node,
                table.get("xpath") or f"/article/body/table-wrap[{index}]",
                index,
                json.dumps(
                    {"tag": "table-wrap", "id": table.get("id") or "", "caption": table.get("caption") or ""},
                    ensure_ascii=False,
                ),
            ),
        )
        table_count += 1

    return {
        "sections": len(data.get("sections") or []),
        "paragraphs": len(data.get("paragraphs") or []),
        "sentences": sentence_count,
        "figures": fig_count,
        "tables": table_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--sqlite-db", default=str(DEFAULT_SQLITE))
    parser.add_argument("--xml-dir", default=str(DEFAULT_XML_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--paper-id", default="")
    parser.add_argument("--file", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn and "scipal_v2" not in args.pg_dsn.split("/")[-1]:
        raise SystemExit("refusing to write to a non-scipal_v2 database")

    import psycopg

    papers = _paper_map(Path(args.sqlite_db))
    files: List[Path] = []
    if args.file:
        files = [Path(args.file)]
    else:
        for path in sorted(Path(args.xml_dir).glob("*.xml")):
            meta = papers.get(path.name)
            if not meta:
                continue
            if args.paper_id and meta["paper_id"] != args.paper_id:
                continue
            files.append(path)
            if args.limit and len(files) >= args.limit:
                break
    totals = {"papers": 0, "sections": 0, "paragraphs": 0, "sentences": 0, "figures": 0, "tables": 0}
    failures = []
    with psycopg.connect(args.pg_dsn) as conn:
        for path in files:
            meta = papers.get(path.name)
            if not meta:
                continue
            try:
                stats = import_one(conn, path, meta)
                conn.commit()
                totals["papers"] += 1
                for key in ("sections", "paragraphs", "sentences", "figures", "tables"):
                    totals[key] += stats[key]
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                failures.append({"file": path.name, "error": str(exc)[:300]})
        if args.dry_run:
            conn.rollback()
    print(
        json.dumps(
            {"totals": totals, "attempted": len(files), "failures": failures[:10], "failure_count": len(failures)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
