"""PG replacement for build_xml_db: import a directory of JATS XML."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_db.import_jats_pg import import_file
from services.db.pg_pool import pg_connection


def _paper_id(pg, filename: str) -> str:
    row = pg.execute(
        "SELECT paper_id FROM papers WHERE filename=%s LIMIT 1", (filename,)
    ).fetchone()
    if row:
        return row[0]
    return "paper_" + Path(filename).stem.replace(".", "_")


def build(xml_dir: Path, limit: int = 0) -> dict:
    files = sorted(xml_dir.glob("*.xml"))
    if limit:
        files = files[:limit]
    pg = pg_connection()
    totals = {"papers": 0, "sections": 0, "paragraphs": 0, "sentences": 0, "links": 0}
    try:
        for xml_path in files:
            pid = _paper_id(pg, xml_path.name)
            stats = import_file(xml_path, pid)
            if not stats:
                continue
            totals["papers"] += 1
            for key in ("sections", "paragraphs", "sentences", "links"):
                totals[key] += stats.get(key, 0)
        return totals
    finally:
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml-dir", default="documents_xml")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    print(build(Path(args.xml_dir), args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
