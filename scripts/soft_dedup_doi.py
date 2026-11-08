"""Mark same-DOI paper parses as soft duplicates.

Keeps every row, sets papers.duplicate_of to the parse with the most paragraphs.
Search paths filter duplicate_of IS NULL.
"""

from __future__ import annotations

import os

from services.db.pg_pool import pg_connection

SQL = """
ALTER TABLE papers ADD COLUMN IF NOT EXISTS duplicate_of TEXT;
CREATE INDEX IF NOT EXISTS idx_papers_duplicate_of
    ON papers (duplicate_of) WHERE duplicate_of IS NOT NULL;

WITH ranked AS (
  SELECT p.paper_id, lower(p.doi) AS doi_key,
         row_number() OVER (
           PARTITION BY lower(p.doi)
           ORDER BY (SELECT count(*) FROM paragraphs x WHERE x.paper_id = p.paper_id) DESC,
                    p.paper_id
         ) AS rn,
         first_value(p.paper_id) OVER (
           PARTITION BY lower(p.doi)
           ORDER BY (SELECT count(*) FROM paragraphs x WHERE x.paper_id = p.paper_id) DESC,
                    p.paper_id
         ) AS canonical
  FROM papers p
  WHERE coalesce(p.doi, '') <> ''
), upd AS (
  SELECT paper_id, canonical FROM ranked WHERE rn > 1
)
UPDATE papers p
SET duplicate_of = upd.canonical
FROM upd
WHERE p.paper_id = upd.paper_id
  AND p.duplicate_of IS DISTINCT FROM upd.canonical;
"""


def main() -> int:
    if os.environ.get("SCIPAL_SEARCH_META_BACKEND", "").strip().lower() not in {
        "postgres", "postgresql", "pg", "1", "true"
    }:
        raise SystemExit("SCIPAL_SEARCH_META_BACKEND must be postgres")
    pg = pg_connection()
    try:
        pg.execute(SQL)
        pg.commit()
        marked = pg.execute(
            "SELECT count(*) AS n FROM papers WHERE duplicate_of IS NOT NULL"
        ).fetchone()
        print(f"marked={marked['n']}")
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
