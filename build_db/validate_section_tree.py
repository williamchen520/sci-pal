"""Validate the materialized section tree (parent_id / depth)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def main() -> int:
    conn = sqlite3.connect(str(DB))
    total = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    roots = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE depth = 1"
    ).fetchone()[0]
    missing_parent = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE depth > 1 "
        "AND (parent_id IS NULL OR parent_id = '')"
    ).fetchone()[0]
    wrong_depth = conn.execute(
        "SELECT COUNT(*) FROM sections c JOIN sections p ON p.section_id = c.parent_id "
        "WHERE c.depth != p.depth + 1"
    ).fetchone()[0]
    orphan = conn.execute(
        "SELECT COUNT(*) FROM sections c LEFT JOIN sections p ON p.section_id = c.parent_id "
        "WHERE c.depth > 1 AND p.section_id IS NULL"
    ).fetchone()[0]
    self_parent = conn.execute(
        "SELECT COUNT(*) FROM sections WHERE section_id = parent_id"
    ).fetchone()[0]
    conn.close()
    print({
        "total": total,
        "roots": roots,
        "missing_parent": missing_parent,
        "wrong_depth": wrong_depth,
        "orphan": orphan,
        "self_parent": self_parent,
    })
    return 0 if not (missing_parent or wrong_depth or orphan or self_parent) else 1


if __name__ == "__main__":
    raise SystemExit(main())
