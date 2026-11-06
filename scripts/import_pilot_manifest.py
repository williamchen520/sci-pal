#!/usr/bin/env python3
"""Import the pilot manifest XML files into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_db.build_xml_db_pg import _paper_id
from build_db.import_jats_pg import import_file
from services.db.pg_pool import pg_connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="F:/scipal_data/pilot_500_manifest.jsonl")
    parser.add_argument("--xml-dir", default="F:/scipal_data/documents_xml")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in Path(args.manifest).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [row for row in rows if row.get("status") == "ok"]
    if args.limit:
        rows = rows[: args.limit]
    pg = pg_connection()
    totals = {"papers": 0, "skipped": 0, "paragraphs": 0, "sentences": 0, "failed": 0}
    try:
        for row in rows:
            path = Path(args.xml_dir) / f"{row['pmcid']}.xml"
            if not path.exists():
                totals["failed"] += 1
                continue
            try:
                existing = pg.execute(
                    "SELECT 1 FROM papers p WHERE p.filename=%s AND EXISTS "
                    "(SELECT 1 FROM paragraphs x WHERE x.paper_id=p.paper_id) LIMIT 1",
                    (path.name,),
                ).fetchone()
                pg.commit()
                if existing:
                    totals["skipped"] += 1
                    continue
                pid = _paper_id(pg, path.name)
                pg.commit()
                stats = import_file(path, pid)
                if stats:
                    totals["papers"] += 1
                    totals["paragraphs"] += stats.get("paragraphs", 0)
                    totals["sentences"] += stats.get("sentences", 0)
                else:
                    totals["failed"] += 1
            except Exception as exc:  # noqa: BLE001
                totals["failed"] += 1
                print(f"{path.name}: {str(exc)[:160]}", flush=True)
        print(totals)
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
