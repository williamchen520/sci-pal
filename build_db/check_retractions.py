"""Check retractions/corrections for papers with DOIs.

Usage:
    python -m build_db.check_retractions --limit 20
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

from build_db.trust_schema import migrate
from services.trust.retraction import check_doi, flag_paper

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def run(db_path: Path | str = DEFAULT_DB, limit: int = 50, delay: float = 0.2) -> dict:
    migrate(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = {"checked": 0, "flagged": 0}
    try:
        rows = conn.execute(
            "SELECT paper_id, doi FROM papers WHERE doi IS NOT NULL AND doi != '' "
            "ORDER BY paper_id LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            flags = check_doi(row["doi"])
            if flags:
                stats["flagged"] += flag_paper(conn, row["paper_id"], flags)
            stats["checked"] += 1
            time.sleep(delay)
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    print(run(args.db, args.limit))
