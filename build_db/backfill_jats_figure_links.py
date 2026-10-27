"""Add jats-regex figure/table links to already-imported XML papers.

New imports get this fallback inside ``import_jats``. This script backfills
papers imported before the fallback existed, without re-parsing XML and
without touching existing ``source='jats'`` links.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

FIG_RE = re.compile(r"\bFig(?:ure)?\.?\s*(\d+)")
TABLE_RE = re.compile(r"\bTable\s*(\d+)")


def backfill(db_path: Path | str = DEFAULT_DB, limit: int = 0) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = {"papers": 0, "links": 0}
    try:
        papers = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT s.paper_id FROM sentences s "
                "JOIN papers p ON p.paper_id = s.paper_id "
                "WHERE p.parse_engine = 'xml'"
            )
        ]
        for paper_id in papers:
            figures = {
                re.search(r"(\d+)", row["fig_number"] or "").group(1): row["fig_id"]
                for row in conn.execute(
                    "SELECT fig_id, fig_number FROM figures WHERE paper_id = ?", (paper_id,)
                )
                if re.search(r"(\d+)", row["fig_number"] or "")
            }
            tables = {
                re.search(r"(\d+)", row["table_number"] or "").group(1): row["table_id"]
                for row in conn.execute(
                    "SELECT table_id, table_number FROM tables WHERE paper_id = ?", (paper_id,)
                )
                if re.search(r"(\d+)", row["table_number"] or "")
            }
            if not figures and not tables:
                continue

            existing = {
                (row[0], row[1], row[2])
                for row in conn.execute(
                    "SELECT sentence_id, target_type, target_id FROM sentence_links "
                    "WHERE paper_id = ?",
                    (paper_id,),
                )
            }
            added = 0
            for row in conn.execute(
                "SELECT sentence_id, para_id, text FROM sentences WHERE paper_id = ?",
                (paper_id,),
            ):
                for number in FIG_RE.findall(row["text"] or ""):
                    target = figures.get(number)
                    key = (row["sentence_id"], "figure", target)
                    if not target or key in existing:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO sentence_links "
                        "(link_id, sentence_id, para_id, paper_id, source_type, target_type, "
                        " target_id, relation, page, bbox, source, confidence) "
                        "VALUES (?, ?, ?, ?, 'sentence', 'figure', ?, 'mentions', "
                        "        NULL, NULL, 'jats-regex', 0.6)",
                        (
                            f"jatsrx_{row['sentence_id']}_figure_{target}",
                            row["sentence_id"],
                            row["para_id"],
                            paper_id,
                            target,
                        ),
                    )
                    existing.add(key)
                    added += 1
                for number in TABLE_RE.findall(row["text"] or ""):
                    target = tables.get(number)
                    key = (row["sentence_id"], "table", target)
                    if not target or key in existing:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO sentence_links "
                        "(link_id, sentence_id, para_id, paper_id, source_type, target_type, "
                        " target_id, relation, page, bbox, source, confidence) "
                        "VALUES (?, ?, ?, ?, 'sentence', 'table', ?, 'mentions', "
                        "        NULL, NULL, 'jats-regex', 0.6)",
                        (
                            f"jatsrx_{row['sentence_id']}_table_{target}",
                            row["sentence_id"],
                            row["para_id"],
                            paper_id,
                            target,
                        ),
                    )
                    existing.add(key)
                    added += 1
            if added:
                stats["papers"] += 1
                stats["links"] += added
            conn.commit()
            if limit and stats["papers"] >= limit:
                break
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(backfill(args.db, limit=args.limit), ensure_ascii=False))
