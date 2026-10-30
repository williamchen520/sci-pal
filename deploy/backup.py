"""Cross-platform backup for SciPal data.

Creates a consistent SQLite copy, then archives the data directory.
Run while the service is idle; SQLite backup is online-safe.
"""

from __future__ import annotations

import argparse
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="backups")
    args = parser.parse_args()
    root = Path(args.data).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = out / f"scipal-{stamp}.tar.gz"
    db = root / "research.db"

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "research.db"
        if db.exists():
            source = sqlite3.connect(db)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(root, arcname="data")
            if snapshot.exists():
                tar.add(snapshot, arcname="data/research.db")
    print(archive)


if __name__ == "__main__":
    main()
