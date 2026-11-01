#!/usr/bin/env python3
"""Persist OpenAlex primary-topic labels into SQLite and CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "eval" / "results" / "openalex_coverage.json"))
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--csv", default=str(ROOT / "eval" / "results" / "openalex_paper_domains.csv"))
    parser.add_argument("--source", default="openalex")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = payload.get("rows") or {}
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    for paper_id, row in sorted(rows.items()):
        records.append(
            (
                paper_id,
                args.source,
                row.get("openalex_id"),
                row.get("doi"),
                row.get("domain_id"),
                row.get("domain_name"),
                row.get("field_id"),
                row.get("field_name"),
                row.get("subfield_id"),
                row.get("subfield_name"),
                row.get("topic_id"),
                row.get("topic_name"),
                1,
                fetched_at,
            )
        )

    csv_path = Path(args.csv)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "paper_id",
                "source",
                "openalex_id",
                "doi",
                "domain_id",
                "domain_name",
                "field_id",
                "field_name",
                "subfield_id",
                "subfield_name",
                "topic_id",
                "topic_name",
                "is_primary",
                "fetched_at",
            ]
        )
        writer.writerows(records)

    conn = sqlite3.connect(args.db)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_domains_openalex (
                paper_id TEXT NOT NULL,
                source TEXT NOT NULL,
                openalex_id TEXT,
                doi TEXT,
                domain_id TEXT,
                domain_name TEXT,
                field_id TEXT,
                field_name TEXT,
                subfield_id TEXT,
                subfield_name TEXT,
                topic_id TEXT,
                topic_name TEXT,
                is_primary INTEGER NOT NULL DEFAULT 1,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (paper_id, source, topic_id)
            )
            """
        )
        conn.execute("DELETE FROM paper_domains_openalex WHERE source = ?", (args.source,))
        conn.executemany(
            """
            INSERT INTO paper_domains_openalex (
                paper_id, source, openalex_id, doi,
                domain_id, domain_name, field_id, field_name,
                subfield_id, subfield_name, topic_id, topic_name,
                is_primary, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        conn.commit()
        total = conn.execute(
            "SELECT count(*) FROM paper_domains_openalex WHERE source = ?", (args.source,)
        ).fetchone()[0]
        unique = conn.execute(
            "SELECT count(distinct paper_id) FROM paper_domains_openalex WHERE source = ?", (args.source,)
        ).fetchone()[0]
    finally:
        conn.close()

    print(json.dumps({"csv": str(csv_path), "rows": len(records), "table": "paper_domains_openalex", "table_rows": total, "unique_papers": unique}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
