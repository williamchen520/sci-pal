"""Structure v2: explicit section tree, geometry columns, unified paper links.

Migration is idempotent: it only adds what is missing.

New tables
----------
sections(section_id, paper_id, parent_id, level, title, seq, page, bbox, source)
paper_links(link_id, source_paper_id, target_paper_id, target_doi, relation,
            evidence_sentence_id, source, confidence)

Added columns
-------------
paragraphs.section_id
sentences.page / bbox / section_id / char_start / char_end
citations.page / bbox
tables.page / bbox
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """Add a column if it does not exist; return True when added."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in existing:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def migrate(db_path: Path | str = DEFAULT_DB) -> dict:
    conn = sqlite3.connect(str(db_path))
    added: list[str] = []
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sections (
                section_id TEXT PRIMARY KEY,
                paper_id   TEXT NOT NULL,
                parent_id  TEXT,
                level      INTEGER,
                title      TEXT,
                seq        INTEGER,
                page       INTEGER,
                bbox       TEXT,
                source     TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sections_paper ON sections(paper_id, seq)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_links (
                link_id              TEXT PRIMARY KEY,
                source_paper_id      TEXT NOT NULL,
                target_paper_id      TEXT,
                target_doi           TEXT,
                relation             TEXT NOT NULL,
                evidence_sentence_id TEXT,
                source               TEXT,
                confidence           REAL DEFAULT 1.0,
                created_at           TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_links_source "
            "ON paper_links(source_paper_id, relation)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paper_links_target "
            "ON paper_links(target_paper_id, relation)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citation_mentions (
                mention_id   TEXT PRIMARY KEY,
                paper_id     TEXT NOT NULL,
                ref_number   TEXT,
                page         INTEGER,
                bbox         TEXT,
                context      TEXT,
                source       TEXT,
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_citation_mentions_paper "
            "ON citation_mentions(paper_id, ref_number)"
        )

        if ensure_column(conn, "paragraphs", "section_id", "TEXT"):
            added.append("paragraphs.section_id")
        if ensure_column(conn, "paragraphs", "section_path", "TEXT"):
            added.append("paragraphs.section_path")
        for column, decl in (
            ("page", "INTEGER"),
            ("bbox", "TEXT"),
            ("section_id", "TEXT"),
            ("char_start", "INTEGER"),
            ("char_end", "INTEGER"),
        ):
            if ensure_column(conn, "sentences", column, decl):
                added.append(f"sentences.{column}")
        for column, decl in (("page", "INTEGER"), ("bbox", "TEXT")):
            if ensure_column(conn, "citations", column, decl):
                added.append(f"citations.{column}")
            if ensure_column(conn, "tables", column, decl):
                added.append(f"tables.{column}")
        for column, decl in (
            ("page", "INTEGER"),
            ("bbox", "TEXT"),
            ("source", "TEXT"),
            ("confidence", "REAL"),
        ):
            if ensure_column(conn, "sentence_links", column, decl):
                added.append(f"sentence_links.{column}")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentences_para_seq "
            "ON sentences(para_id, sequence)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentence_links_sentence "
            "ON sentence_links(sentence_id)"
        )
        conn.commit()
    finally:
        conn.close()
    return {"added_columns": added}


def main() -> int:
    result = migrate()
    if result["added_columns"]:
        print("added columns:", ", ".join(result["added_columns"]))
    else:
        print("schema already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
