"""Create a PostgreSQL unified_papers compatibility view."""

from __future__ import annotations

import argparse
import os

from services.db.pg_pool import pg_connection


def build_view(dsn: str = "") -> dict:
    pg = pg_connection(dsn or os.environ.get("SCIPAL_PG_DSN", ""))
    try:
        pg.execute(
            """
            CREATE OR REPLACE VIEW unified_papers AS
            SELECT paper_id,
                   NULL::text AS pmcid,
                   NULL::text AS pmid,
                   doi,
                   title,
                   authors,
                   abstract,
                   journal,
                   year::text AS publish_date,
                   'papers'::text AS source_db
            FROM papers
            """
        )
        pg.commit()
        row = pg.execute("SELECT count(*) AS n FROM unified_papers").fetchone()
        count = row["n"] if isinstance(row, dict) else row[0]
        return {"papers": count}
    finally:
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    args = parser.parse_args()
    print(build_view(args.dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
