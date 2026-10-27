"""Structure integrity audit (and optional cleanup).

Checks for dangling references that break the "tree" guarantees:

* sections whose parent is missing
* paragraphs whose section is missing / belongs to another paper
* sentences whose paragraph or paper is missing
* citations/figures/tables whose paper is missing
* sentence_links whose sentence is missing

Usage:
    python -m build_db.audit_structure
    python -m build_db.audit_structure --fix
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

CHECKS = {
    "orphan_section_parent": (
        "SELECT COUNT(*) FROM sections s WHERE s.parent_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM sections p WHERE p.section_id=s.parent_id AND p.paper_id=s.paper_id)"
    ),
    "paragraph_section_missing": (
        "SELECT COUNT(*) FROM paragraphs pa WHERE pa.section_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM sections s WHERE s.section_id=pa.section_id AND s.paper_id=pa.paper_id)"
    ),
    "paragraph_paper_missing": (
        "SELECT COUNT(*) FROM paragraphs pa WHERE NOT EXISTS "
        "(SELECT 1 FROM papers p WHERE p.paper_id=pa.paper_id)"
    ),
    "sentence_paragraph_missing": (
        "SELECT COUNT(*) FROM sentences se WHERE NOT EXISTS "
        "(SELECT 1 FROM paragraphs pa WHERE pa.para_id=se.para_id)"
    ),
    "sentence_paper_missing": (
        "SELECT COUNT(*) FROM sentences se WHERE NOT EXISTS "
        "(SELECT 1 FROM papers p WHERE p.paper_id=se.paper_id)"
    ),
    "citation_paper_missing": (
        "SELECT COUNT(*) FROM citations c WHERE NOT EXISTS "
        "(SELECT 1 FROM papers p WHERE p.paper_id=c.paper_id)"
    ),
    "figure_paper_missing": (
        "SELECT COUNT(*) FROM figures f WHERE NOT EXISTS "
        "(SELECT 1 FROM papers p WHERE p.paper_id=f.paper_id)"
    ),
    "table_paper_missing": (
        "SELECT COUNT(*) FROM tables t WHERE NOT EXISTS "
        "(SELECT 1 FROM papers p WHERE p.paper_id=t.paper_id)"
    ),
    "link_sentence_missing": (
        "SELECT COUNT(*) FROM sentence_links sl WHERE NOT EXISTS "
        "(SELECT 1 FROM sentences s WHERE s.sentence_id=sl.sentence_id)"
    ),
}


def audit(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {name: conn.execute(sql).fetchone()[0] for name, sql in CHECKS.items()}
    finally:
        conn.close()


def fix(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    removed = {"sentences": 0, "links": 0}
    try:
        removed["links"] = conn.execute(
            "DELETE FROM sentence_links WHERE NOT EXISTS "
            "(SELECT 1 FROM sentences s WHERE s.sentence_id=sentence_links.sentence_id)"
        ).rowcount
        removed["sentences"] = conn.execute(
            "DELETE FROM sentences WHERE NOT EXISTS "
            "(SELECT 1 FROM paragraphs pa WHERE pa.para_id=sentences.para_id)"
        ).rowcount
        removed["links"] += conn.execute(
            "DELETE FROM sentence_links WHERE NOT EXISTS "
            "(SELECT 1 FROM sentences s WHERE s.sentence_id=sentence_links.sentence_id)"
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    return removed


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    if args.fix:
        print("removed:", json.dumps(fix(args.db), ensure_ascii=False))
    print(json.dumps(audit(args.db), ensure_ascii=False, indent=2))
