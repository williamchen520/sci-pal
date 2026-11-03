"""Cross-platform backup for SciPal data.

Scopes:
  db    only the consistent SQLite snapshot (small, daily)
  full  data directory + SQLite snapshot (larger, weekly)

Run while the service is idle; SQLite backup is online-safe.
"""

from __future__ import annotations

import argparse
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _exclude_live_db(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Do not archive the live SQLite file; the snapshot is added instead."""
    name = tarinfo.name.replace("\\", "/")
    if name in {"data/research.db", "data/research.db-wal", "data/research.db-shm"}:
        return None
    return tarinfo


def create_archive(
    data: str | Path = "data",
    out: str | Path = "backups",
    *,
    scope: str = "full",
) -> Path:
    """Create one verified snapshot archive and return its path."""
    if scope not in {"db", "full"}:
        raise ValueError("scope must be 'db' or 'full'")
    root = Path(data).resolve()
    out_dir = Path(out).resolve()
    if not root.exists():
        raise FileNotFoundError(f"data directory not found: {root}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = out_dir / f"scipal-{scope}-{stamp}.tar.gz"
    if archive.exists():
        raise FileExistsError(f"refusing to overwrite archive: {archive}")
    db = root / "research.db"

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "research.db"
        if db.exists():
            source = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        with tarfile.open(archive, "w:gz") as tar:
            if scope == "full":
                tar.add(root, arcname="data", filter=_exclude_live_db)
            if snapshot.exists():
                tar.add(snapshot, arcname="data/research.db")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="backups")
    parser.add_argument("--scope", choices=("db", "full"), default="full")
    args = parser.parse_args()
    print(create_archive(args.data, args.out, scope=args.scope))


if __name__ == "__main__":
    main()
