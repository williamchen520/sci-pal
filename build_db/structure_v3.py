"""Structure v3: materialized section paths + lookup indexes + sentence FTS.

Adds:

* ``sections.path`` ("1.2.3") and ``sections.depth``
* lookup indexes for section/paragraph/sentence/figure/table/citation
* ``sentences_fts`` (FTS5, external content on ``sentences``) with fast
  rowid-based triggers

Idempotent: safe to re-run. Use after bulk imports to refresh paths/FTS.

Usage:
    python -m build_db.structure_v3
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in existing:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def assign_paths_for_paper(conn: sqlite3.Connection, paper_id: str) -> int:
    """Recompute path/depth for one paper from parent_id + seq."""
    rows = conn.execute(
        "SELECT section_id, parent_id, seq FROM sections WHERE paper_id = ? ORDER BY seq",
        (paper_id,),
    ).fetchall()
    if not rows:
        return 0
    ids = {row[0] for row in rows}
    children: Dict[str | None, List[str]] = {}
    for section_id, parent_id, _seq in rows:
        parent = parent_id if parent_id in ids else None
        children.setdefault(parent, []).append(section_id)

    updates: List[Tuple[str, int, str]] = []
    stack: List[Tuple[str, str, int]] = []
    for index, root in enumerate(children.get(None, []), 1):
        stack.append((root, str(index), 1))
    while stack:
        section_id, path, depth = stack.pop()
        updates.append((path, depth, section_id))
        kids = children.get(section_id, [])
        for index in range(len(kids) - 1, -1, -1):
            stack.append((kids[index], f"{path}.{index + 1}", depth + 1))
    conn.executemany(
        "UPDATE sections SET path = ?, depth = ? WHERE section_id = ?", updates
    )
    return len(updates)


def _create_indexes(conn: sqlite3.Connection) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(paper_id, parent_id, seq)",
        "CREATE INDEX IF NOT EXISTS idx_sections_path ON sections(paper_id, path)",
        "CREATE INDEX IF NOT EXISTS idx_paragraphs_section ON paragraphs(section_id, sequence)",
        "CREATE INDEX IF NOT EXISTS idx_sentences_section ON sentences(section_id, sequence)",
        "CREATE INDEX IF NOT EXISTS idx_figures_number ON figures(paper_id, fig_number)",
        "CREATE INDEX IF NOT EXISTS idx_tables_number ON tables(paper_id, table_number)",
        "CREATE INDEX IF NOT EXISTS idx_citations_number ON citations(paper_id, ref_number)",
    ]
    for sql in statements:
        conn.execute(sql)


def _create_sentence_fts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS sentences_fts USING fts5(
            sentence_id, paper_id, section_id, text,
            content='sentences', content_rowid='rowid'
        )
        """
    )
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS sentences_ai AFTER INSERT ON sentences BEGIN
            INSERT INTO sentences_fts(rowid, sentence_id, paper_id, section_id, text)
            VALUES (new.rowid, new.sentence_id, new.paper_id, new.section_id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS sentences_ad AFTER DELETE ON sentences BEGIN
            INSERT INTO sentences_fts(sentences_fts, rowid, sentence_id, paper_id, section_id, text)
            VALUES ('delete', old.rowid, old.sentence_id, old.paper_id, old.section_id, old.text);
        END;
        CREATE TRIGGER IF NOT EXISTS sentences_au AFTER UPDATE ON sentences BEGIN
            INSERT INTO sentences_fts(sentences_fts, rowid, sentence_id, paper_id, section_id, text)
            VALUES ('delete', old.rowid, old.sentence_id, old.paper_id, old.section_id, old.text);
            INSERT INTO sentences_fts(rowid, sentence_id, paper_id, section_id, text)
            VALUES (new.rowid, new.sentence_id, new.paper_id, new.section_id, new.text);
        END;
        """
    )
    # always rebuild: external-content FTS COUNT(*) reads the content table,
    # so it cannot tell whether the index itself is populated
    conn.execute("INSERT INTO sentences_fts(sentences_fts) VALUES ('rebuild')")


def migrate(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    stats = {"paths": 0, "papers": 0, "fts": 0}
    try:
        ensure_column(conn, "sections", "path", "TEXT")
        ensure_column(conn, "sections", "depth", "INTEGER")
        papers = [
            row[0]
            for row in conn.execute("SELECT DISTINCT paper_id FROM sections")
        ]
        for paper_id in papers:
            count = assign_paths_for_paper(conn, paper_id)
            if count:
                stats["paths"] += count
                stats["papers"] += 1
        _create_indexes(conn)
        _create_sentence_fts(conn)
        stats["fts"] = conn.execute("SELECT COUNT(*) FROM sentences_fts").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return stats


def refresh_for_paper(conn: sqlite3.Connection, paper_id: str) -> int:
    """Recompute a single paper's paths (used after section rebuild/import)."""
    ensure_column(conn, "sections", "path", "TEXT")
    ensure_column(conn, "sections", "depth", "INTEGER")
    return assign_paths_for_paper(conn, paper_id)


if __name__ == "__main__":
    print(migrate())
