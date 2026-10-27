"""Backfill GROBID in-text citation positions for legacy PDF papers.

Older PDF imports (parse_engine NULL/docling) have no ``citation_mentions``;
their sentence-level citation links are regex-only. This script re-runs GROBID
on the local PDF, stores page/bbox mentions, and rebuilds sentence links so
authoritative positions (source='grobid', 0.9) replace the regex guesses.

Usage:
    python -m build_db.backfill_grobid_mentions --limit 10
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Dict

from build_db.rebuild_sentence_links import build_for_paper as rebuild_links
from build_db.parsers.grobid_parser import GrobidParser
from build_db.parsers.pipeline import resolve_grobid_url

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
DOCUMENTS = Path(__file__).resolve().parent.parent / "documents"


def backfill(
    db_path: Path | str = DEFAULT_DB,
    limit: int = 0,
    only_missing: bool = True,
) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    parser = GrobidParser(resolve_grobid_url("crf"))
    stats = {"papers": 0, "mentions": 0, "links": 0, "failed": 0, "skipped": 0}
    try:
        query = (
            "SELECT paper_id, filename FROM papers "
            "WHERE filename LIKE '%.pdf' AND COALESCE(parse_engine, '') != 'mineru'"
        )
        if only_missing:
            query += (
                " AND NOT EXISTS (SELECT 1 FROM citation_mentions m "
                "WHERE m.paper_id = papers.paper_id)"
            )
        for row in conn.execute(query).fetchall():
            pdf_path = DOCUMENTS / row["filename"]
            if not pdf_path.exists():
                stats["skipped"] += 1
                continue
            try:
                result = parser.parse(str(pdf_path))
            except Exception:  # noqa: BLE001
                stats["failed"] += 1
                continue
            mentions = [
                m for m in (result.get("intext_citations") or [])
                if m.get("ref_number")
            ]
            conn.execute(
                "DELETE FROM citation_mentions WHERE paper_id = ?", (row["paper_id"],)
            )
            for index, mention in enumerate(mentions, 1):
                conn.execute(
                    "INSERT OR REPLACE INTO citation_mentions "
                    "(mention_id, paper_id, ref_number, page, bbox, context, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'grobid')",
                    (
                        f"mention_{row['paper_id']}_{index:04d}",
                        row["paper_id"],
                        mention.get("ref_number"),
                        mention.get("page"),
                        mention.get("bbox"),
                        mention.get("context"),
                    ),
                )
            conn.commit()
            stats["mentions"] += len(mentions)
            link_stats = rebuild_links(db_path, row["paper_id"])
            stats["links"] += link_stats.get("citations", 0)
            stats["papers"] += 1
            print(
                f"{row['filename']}: {len(mentions)} mentions, "
                f"{link_stats.get('citations', 0)} citation links",
                flush=True,
            )
            if limit and stats["papers"] >= limit:
                break
            time.sleep(0.2)
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            backfill(args.db, limit=args.limit, only_missing=not args.all),
            ensure_ascii=False,
        )
    )
