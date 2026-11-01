#!/usr/bin/env python3
"""Import metadata-only XML papers (no source file) into scipal_v2.

These papers keep titles/authors/abstract, but have no documents/source_nodes/
sections/sentences. They must not be treated as full text.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--sqlite-db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--xml-dir", default=str(ROOT / "documents_xml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if "scipal_v2" not in args.pg_dsn:
        raise SystemExit("refusing to write a non-scipal_v2 database")

    files = {path.name for path in Path(args.xml_dir).glob("*.xml")}
    conn = sqlite3.connect(f"file:{args.sqlite_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT paper_id, filename, workspace_id, title, authors, abstract, journal, year, doi "
            "FROM papers WHERE parse_engine='xml' AND filename IS NOT NULL"
        )
        if row["filename"] not in files
    ]
    conn.close()

    import psycopg

    inserted = 0
    existing = 0
    with psycopg.connect(args.pg_dsn) as pg:
        for row in rows:
            exists = pg.execute(
                "SELECT 1 FROM papers WHERE paper_id=%s", (row["paper_id"],)
            ).fetchone()
            if exists:
                existing += 1
                continue
            pg.execute(
                """INSERT INTO papers
                   (paper_id, workspace_id, title, authors, journal, year, doi, abstract,
                    parse_status, fulltext_status, source_flags)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'metadata_only','metadata_only',%s)""",
                (
                    row["paper_id"],
                    row.get("workspace_id") or "ws_default",
                    row.get("title") or "",
                    row.get("authors") or "",
                    row.get("journal") or "",
                    row.get("year"),
                    row.get("doi") or "",
                    row.get("abstract") or "",
                    json.dumps(
                        {
                            "has_xml": False,
                            "has_pdf": False,
                            "fulltext": "missing",
                            "coordinate_source": "unavailable",
                        }
                    ),
                ),
            )
            inserted += 1
        if args.dry_run:
            pg.rollback()
        else:
            pg.commit()
    report = {
        "missing_source": len(rows),
        "inserted": inserted,
        "existing": existing,
        "dry_run": args.dry_run,
        "fulltext_status": "metadata_only",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
