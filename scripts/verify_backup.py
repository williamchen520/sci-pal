#!/usr/bin/env python3
"""Verify a SciPal backup archive and optionally restore its SQLite DB.

Checks:
  * archive contains data/research.db
  * PRAGMA integrity_check == ok
  * papers table is readable
  * optional expected paper count matches
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import tarfile
import tempfile
from pathlib import Path


def _extract_db(archive: Path, destination: Path) -> Path:
    with tarfile.open(archive, "r:gz") as tar:
        members = [m for m in tar.getmembers() if m.name.replace("\\", "/") == "data/research.db"]
        if not members:
            raise FileNotFoundError("archive has no data/research.db")
        member = members[-1]
        source = tar.extractfile(member)
        if source is None:
            raise FileNotFoundError("archive member is not a regular file")
        with destination.open("wb") as target:
            target.write(source.read())
    return destination


def verify_archive(archive: str | Path, *, expected_papers: int | None = None) -> dict:
    archive = Path(archive)
    if not archive.exists():
        raise FileNotFoundError(f"archive not found: {archive}")
    with tempfile.TemporaryDirectory() as tmp:
        db = _extract_db(archive, Path(tmp) / "research.db")
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            papers = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        finally:
            conn.close()
    ok = integrity == "ok" and (expected_papers is None or papers == expected_papers)
    return {
        "archive": str(archive),
        "integrity": integrity,
        "papers": papers,
        "expected_papers": expected_papers,
        "ok": ok,
    }


def restore_archive(archive: str | Path, target: str | Path, *, force: bool = False) -> Path:
    archive = Path(archive)
    target = Path(target)
    if target.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {target}; pass --force")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        db = _extract_db(archive, Path(tmp) / "research.db")
        target.write_bytes(db.read_bytes())
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--expected-papers", type=int, default=None)
    parser.add_argument("--restore-to", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = verify_archive(args.archive, expected_papers=args.expected_papers)
    if args.restore_to and result["ok"]:
        result["restored_to"] = str(
            restore_archive(args.archive, args.restore_to, force=args.force)
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
