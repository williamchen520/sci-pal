#!/usr/bin/env python3
"""Build PostgreSQL FTS term-frequency stats for rare-term query selection."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.db.pg_pool import close_pools, pg_connection  # noqa: E402

SOURCES = {
    "paragraphs": "paragraphs",
    "summaries": "summaries",
    "sentences": "sentences",
}
DDL = """
CREATE TABLE IF NOT EXISTS fts_term_stats (
    source TEXT NOT NULL,
    word TEXT NOT NULL,
    ndoc INTEGER NOT NULL,
    nentry BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, word)
);
CREATE INDEX IF NOT EXISTS fts_term_stats_rarity_idx
    ON fts_term_stats (source, nentry);
"""


def build(dsn: str, *, sources: list[str] | None = None) -> dict:
    selected = sources or list(SOURCES)
    out = {}
    with pg_connection(dsn) as pg:
        pg.execute(DDL)
        for source in selected:
            table = SOURCES[source]
            pg.execute("DELETE FROM fts_term_stats WHERE source = %s", (source,))
            rows = pg.execute(
                f"SELECT word, ndoc, nentry FROM ts_stat('SELECT search_vector FROM {table}')"
            ).fetchall()
            with pg.cursor() as cur:
                cur.executemany(
                    "INSERT INTO fts_term_stats (source, word, ndoc, nentry) VALUES (%s, %s, %s, %s)",
                    [(source, row["word"], row["ndoc"], row["nentry"]) for row in rows],
                )
            out[source] = len(rows)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--source", action="append", choices=tuple(SOURCES), default=[])
    args = parser.parse_args()
    if not args.pg_dsn:
        print("--pg-dsn or SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    result = build(args.pg_dsn, sources=args.source or None)
    close_pools()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
