"""Ensure PostgreSQL full-text indexes exist (PG replacement for build_fts)."""

from __future__ import annotations

import argparse
import os

from services.db.pg_pool import pg_connection

INDEXES = {
    "paragraphs": "paragraphs_search_idx",
    "sentences": "sentences_search_idx",
    "papers": "papers_search_idx",
}


def ensure_indexes(dsn: str = "", reindex: bool = False) -> dict:
    pg = pg_connection(dsn or os.environ.get("SCIPAL_PG_DSN", ""))
    try:
        for table, index in INDEXES.items():
            pg.execute(
                f'CREATE INDEX IF NOT EXISTS {index} ON "{table}" USING gin (search_vector)'
            )
            if reindex:
                pg.execute(f'REINDEX INDEX {index}')
        pg.execute("ANALYZE paragraphs")
        pg.execute("ANALYZE sentences")
        pg.execute("ANALYZE papers")
        pg.commit()
        counts = {}
        for table in INDEXES:
            row = pg.execute(
                f'SELECT count(*) AS n FROM "{table}"'
            ).fetchone()
            counts[table] = row["n"] if isinstance(row, dict) else row[0]
        return counts
    finally:
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args()
    print(ensure_indexes(args.dsn, reindex=args.reindex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
