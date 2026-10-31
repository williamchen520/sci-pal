#!/usr/bin/env python3
"""Create a verified SQLite snapshot without touching the source database.

Usage:
    python scripts/backup_sqlite.py
    python scripts/backup_sqlite.py --source data/research.db --dest-dir backups

The source is opened read-only by SQLite; VACUUM INTO writes a new file.
The script refuses to overwrite an existing snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "data" / "research.db"
DEFAULT_DEST = ROOT / "backups"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(source: Path, dest_dir: Path) -> dict:
    source = Path(source)
    dest_dir = Path(dest_dir)
    if not source.exists():
        raise FileNotFoundError(f"source database not found: {source}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{source.stem}_{stamp}.db"
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite snapshot: {dest}")

    conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        conn.execute("VACUUM INTO ?", (str(dest),))
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()

    check = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    try:
        backup_integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        papers = check.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    finally:
        check.close()

    return {
        "source": str(source),
        "dest": str(dest),
        "bytes": dest.stat().st_size,
        "source_integrity": integrity,
        "backup_integrity": backup_integrity,
        "papers": papers,
        "sha256": sha256(dest),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--dest-dir", default=str(DEFAULT_DEST))
    args = parser.parse_args()
    result = create_backup(Path(args.source), Path(args.dest_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["backup_integrity"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
