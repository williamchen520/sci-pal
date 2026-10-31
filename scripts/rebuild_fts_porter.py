#!/usr/bin/env python3
"""Rebuild paragraph/paper FTS with the porter tokenizer in a COPY.

The source snapshot is never modified. The target is a separate database that
can be benchmarked before any production swap.

Usage:
    python scripts/rebuild_fts_porter.py \
      --source backups/research_20261031_210616.db \
      --target backups/research_porter.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.etl import assert_snapshot  # noqa: E402
from build_db.build_fts import (  # noqa: E402
    rebuild_papers_triggers,
    rebuild_paragraphs_triggers,
)

PARAGRAPHS_SQL = """
CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
  para_id UNINDEXED,
  paper_id UNINDEXED,
  section_l1,
  section_l2,
  text,
  tokenize='porter'
)
"""

PAPERS_SQL = """
CREATE VIRTUAL TABLE papers_fts USING fts5(
  paper_id UNINDEXED,
  title,
  authors,
  journal,
  tokenize='porter'
)
"""


def copy_database(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite target: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def rebuild(target: Path) -> dict:
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        # Drop triggers first: they reference the old FTS tables.
        for name in ("paragraphs_ai", "paragraphs_ad", "paragraphs_au",
                     "papers_ai", "papers_ad", "papers_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        conn.execute("DROP TABLE IF EXISTS paragraphs_fts")
        conn.execute("DROP TABLE IF EXISTS papers_fts")
        conn.execute(PARAGRAPHS_SQL)
        conn.execute(PAPERS_SQL)

        rows = conn.execute(
            "SELECT para_id, paper_id, section_level1, section_level2, text "
            "FROM paragraphs WHERE text IS NOT NULL AND length(text) > 10"
        ).fetchall()
        conn.executemany(
            "INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (r["para_id"], r["paper_id"], r["section_level1"] or "",
                 r["section_level2"] or "", r["text"])
                for r in rows
            ],
        )
        papers = conn.execute(
            "SELECT paper_id, title, authors, journal FROM papers"
        ).fetchall()
        conn.executemany(
            "INSERT INTO papers_fts (paper_id, title, authors, journal) VALUES (?, ?, ?, ?)",
            [
                (p["paper_id"], p["title"] or "", p["authors"] or "", p["journal"] or "")
                for p in papers
            ],
        )
        rebuild_paragraphs_triggers(conn)
        rebuild_papers_triggers(conn)
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "target": str(target),
            "paragraphs_indexed": len(rows),
            "papers_indexed": len(papers),
            "paragraphs_fts_rows": conn.execute(
                "SELECT COUNT(*) FROM paragraphs_fts"
            ).fetchone()[0],
            "papers_fts_rows": conn.execute("SELECT COUNT(*) FROM papers_fts").fetchone()[0],
            "integrity": integrity,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite snapshot (not data/research.db)")
    parser.add_argument("--target", required=True, help="new database to create")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    source = assert_snapshot(args.source)
    target = Path(args.target)
    copy_database(source, target)
    report = rebuild(target)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["integrity"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
