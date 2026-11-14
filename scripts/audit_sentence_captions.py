#!/usr/bin/env python3
"""Find sentences that still carry inline figure/table captions, optionally rebuild."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.sentences import build_for_paper

CAPTION_SQL = """
SELECT paper_id, count(*) AS n
FROM sentences
WHERE text ~* '(Fig[.]?|Figure|Table)[[:space:]]+[0-9]+[A-Za-z]?[[:space:]]*[|]'
GROUP BY paper_id
ORDER BY n DESC
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(CAPTION_SQL).fetchall()
    total = sum(int(row[1]) for row in rows)
    print(f"CAPTION_AUDIT papers={len(rows)} sentences={total}")
    for paper_id, count in rows[:20]:
        print(f"  {paper_id} {count}")
    if not args.rebuild:
        return 0
    for paper_id, _ in rows[: args.limit or None]:
        result = build_for_paper(paper_id=paper_id, dsn=args.dsn, replace=True)
        print(f"  REBUILT {paper_id} sentences={result['sentences']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
