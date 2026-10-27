"""Backfill paper metadata from Crossref (DOI first, then title search).

Fills only empty fields; never overwrites existing values.

Usage:
    python -m build_db.backfill_metadata --limit 10 --dry-run
    python -m build_db.backfill_metadata --limit 100
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

from services.search.metadata_sources import crossref_search, crossref_work

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def _needs_backfill(row: sqlite3.Row) -> bool:
    return not any(
        [
            (row["journal"] or "").strip(),
            row["year"],
            (row["doi"] or "").strip(),
            (row["authors"] or "").strip(),
        ]
    ) or not (row["journal"] or "").strip()


def backfill(
    db_path: Path | str = DEFAULT_DB,
    limit: int = 50,
    dry_run: bool = False,
    pause: float = 0.2,
) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats: Dict[str, Any] = {
        "checked": 0,
        "updated": 0,
        "no_match": 0,
        "failed": 0,
        "fields": {"journal": 0, "year": 0, "doi": 0, "authors": 0},
    }
    try:
        rows = conn.execute(
            "SELECT paper_id, title, journal, year, doi, authors FROM papers "
            "WHERE COALESCE(title, '') != '' "
            "AND (COALESCE(journal, '') = '' OR year IS NULL "
            "     OR COALESCE(doi, '') = '' OR COALESCE(authors, '') = '') "
            "ORDER BY paper_id LIMIT ?",
            (limit,),
        ).fetchall()

        for row in rows:
            stats["checked"] += 1
            try:
                meta = {}
                if (row["doi"] or "").strip():
                    meta = crossref_work(row["doi"])
                if not meta or not meta.get("journal"):
                    found = crossref_search(row["title"])
                    if found:
                        meta = {**found, **{k: v for k, v in meta.items() if v}}
            except Exception:  # noqa: BLE001
                stats["failed"] += 1
                continue
            if not meta:
                stats["no_match"] += 1
                continue

            updates = {}
            if not (row["journal"] or "").strip() and meta.get("journal"):
                updates["journal"] = meta["journal"]
            if row["year"] is None and meta.get("year"):
                updates["year"] = meta["year"]
            if not (row["doi"] or "").strip() and meta.get("doi"):
                updates["doi"] = meta["doi"]
            if not (row["authors"] or "").strip() and meta.get("authors"):
                updates["authors"] = "; ".join(meta["authors"])[:1000]

            if updates:
                stats["updated"] += 1
                for key in updates:
                    stats["fields"][key] += 1
                if not dry_run:
                    assignments = ", ".join(f"{key} = ?" for key in updates)
                    conn.execute(
                        f"UPDATE papers SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                        "WHERE paper_id = ?",
                        [*updates.values(), row["paper_id"]],
                    )
            else:
                stats["no_match"] += 1
            time.sleep(pause)
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            backfill(args.db, limit=args.limit, dry_run=args.dry_run),
            ensure_ascii=False,
        )
    )
