"""Build an explicit section tree from paragraph heading paths.

Docling paragraphs carry ``section_path`` (JSON list of headings); legacy rows
only have ``section_level1/2/3``. Either way we materialise a ``sections``
table with parent links and bind every paragraph to its deepest section.

    sect_<paper>_0001  (level 1)
      sect_<paper>_0002  (level 2, parent=0001)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def _heading_path(row: sqlite3.Row) -> List[str]:
    raw = row["section_path"]
    if raw:
        try:
            path = json.loads(raw)
            if isinstance(path, list):
                return [str(p).strip() for p in path if str(p).strip()]
        except (TypeError, ValueError):
            pass
    parts = [row["section_level1"], row["section_level2"], row["section_level3"]]
    path = []
    for part in parts:
        text = (part or "").strip()
        if text and text not in path:
            path.append(text)
    return path


def build_for_paper(db_path: Path | str, paper_id: str) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = {"sections": 0, "paragraphs": 0, "bound": 0}
    try:
        rows = conn.execute(
            "SELECT para_id, section_path, section_level1, section_level2, "
            "section_level3, page, bbox FROM paragraphs "
            "WHERE paper_id = ? ORDER BY sequence",
            (paper_id,),
        ).fetchall()
        if not rows:
            return stats

        conn.execute("DELETE FROM sections WHERE paper_id = ?", (paper_id,))
        path_ids: Dict[Tuple[str, ...], str] = {}
        section_rows: List[Tuple[Any, ...]] = []
        para_map: List[Tuple[str, Any]] = []
        seq = 0
        for row in rows:
            path = _heading_path(row)
            parent_id = None
            for depth in range(1, len(path) + 1):
                key = tuple(path[:depth])
                if key not in path_ids:
                    seq += 1
                    section_id = f"sec_{paper_id}_{seq:04d}"
                    path_ids[key] = section_id
                    section_rows.append(
                        (
                            section_id,
                            paper_id,
                            parent_id,
                            depth,
                            path[depth - 1],
                            seq,
                            row["page"],
                            row["bbox"],
                            "docling" if row["section_path"] else "legacy",
                        )
                    )
                parent_id = path_ids[key]

            section_id = path_ids[tuple(path)] if path else None
            para_map.append((row["para_id"], section_id))
            stats["paragraphs"] += 1
            if section_id:
                stats["bound"] += 1

        if section_rows:
            conn.executemany(
                "INSERT INTO sections "
                "(section_id, paper_id, parent_id, level, title, seq, page, bbox, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                section_rows,
            )
        # ``paragraphs_au`` re-indexes FTS on every UPDATE and its DELETE has no
        # index on para_id (full FTS scan per row). Drop it for the bulk update
        # and restore it in the same transaction.
        trigger_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='paragraphs_au'"
        ).fetchone()
        if trigger_sql:
            conn.execute("DROP TRIGGER paragraphs_au")
        try:
            conn.executemany(
                "UPDATE paragraphs SET section_id = ? WHERE para_id = ?",
                [(sid, para_id) for para_id, sid in para_map],
            )
        finally:
            if trigger_sql:
                conn.execute(trigger_sql[0])
        stats["sections"] = len(section_rows)
        conn.commit()
    finally:
        conn.close()
    return stats


def build_all(db_path: Path | str = DEFAULT_DB, limit: int = 0) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    papers = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT p.paper_id FROM paragraphs p "
            "JOIN papers pp ON pp.paper_id = p.paper_id "
            "WHERE COALESCE(pp.parse_engine, '') != 'xml' ORDER BY p.paper_id"
        )
    ]
    conn.close()
    total = {"papers": 0, "sections": 0, "paragraphs": 0, "bound": 0}
    for paper_id in papers:
        stats = build_for_paper(db_path, paper_id)
        if not stats["paragraphs"]:
            continue
        total["papers"] += 1
        for key in ("sections", "paragraphs", "bound"):
            total[key] += stats[key]
        if limit and total["papers"] >= limit:
            break
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--paper-id")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.paper_id:
        print(build_for_paper(args.db, args.paper_id))
    else:
        print(build_all(args.db, limit=args.limit))
