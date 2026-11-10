"""COPY-level rebuild importer CLI."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_db.import_jats_copy import CopyImporter  # noqa: E402
from services.db.pg_pool import pg_connection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml-dir", default="/app/documents_xml")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=0)
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()
    files = sorted(Path(args.xml_dir).glob("*.xml"))
    files = files[args.start : args.end or None]
    pg = pg_connection()
    importer = CopyImporter(pg, args.batch)
    try:
        for index, path in enumerate(files, 1):
            try:
                importer.add(path)
            except Exception as exc:  # noqa: BLE001
                print(f"skip {path.name}: {exc}", flush=True)
                importer.rows = {key: [] for key in importer.rows}
                importer.papers = 0
        importer.close()
        print(importer.stats, flush=True)
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
