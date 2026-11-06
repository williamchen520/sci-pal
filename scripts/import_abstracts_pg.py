#!/usr/bin/env python3
"""Import abstracts.db into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sqlite3

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="data/abstracts.db")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    src = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    rows = src.execute(
        "SELECT pmid, doi, title, abstract, authors, journal, year, topic, source FROM papers"
    ).fetchall()
    src.close()
    if args.limit:
        rows = rows[: args.limit]

    pg = psycopg.connect(args.dsn)
    try:
        with pg.cursor() as cur:
            cur.executemany(
                "INSERT INTO abstracts (pmid,doi,title,abstract,authors,journal,year,topic,source) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (pmid) DO UPDATE SET doi=EXCLUDED.doi, title=EXCLUDED.title, "
                "abstract=EXCLUDED.abstract, authors=EXCLUDED.authors, journal=EXCLUDED.journal, "
                "year=EXCLUDED.year, topic=EXCLUDED.topic, source=EXCLUDED.source",
                rows,
            )
        pg.commit()
        count = pg.execute("SELECT count(*) FROM abstracts").fetchone()[0]
        print({"source": len(rows), "postgres": count})
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
