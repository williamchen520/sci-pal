"""PG replacement for build_database: parse PDFs into PostgreSQL."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from build_db.parse_service import parse_and_store
from services.db.pg_pool import pg_connection


def build(input_dir: Path, db_path: Path, limit: int = 0) -> dict:
    pdfs = sorted(input_dir.glob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    pg = pg_connection()
    totals = {"papers": 0, "skipped": 0}
    try:
        existing = {
            row[0] for row in pg.execute("SELECT filename FROM papers").fetchall()
        }
        for pdf in pdfs:
            if pdf.name in existing:
                totals["skipped"] += 1
                continue
            stats = parse_and_store(db_path, pdf, pdf.name)
            if stats.get("paper_id"):
                totals["papers"] += 1
        return totals
    finally:
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="documents")
    parser.add_argument("--db", default="data/research.db")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if os.environ.get("SCIPAL_INGEST_PG_ONLY", "").strip().lower() not in {
        "1", "true", "yes", "on"
    }:
        raise SystemExit("SCIPAL_INGEST_PG_ONLY=1 is required")
    print(build(Path(args.input_dir), Path(args.db), args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
