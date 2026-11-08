"""Audit owner-connection usage: only the approved write boundary may use it."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {
    "services/db/pg_pool.py",
    "services/papers/pg_writes.py",
    "services/papers/pg_links.py",
    "build_db/import_jats_pg.py",
    "services/search/ingest.py",
    "services/trust/retraction.py",
    "services/tenancy/service.py",
}
PATTERN = re.compile(r"owner_connection\s*\(")


def main() -> int:
    violations = []
    for base in ("services", "build_db", "routes"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if PATTERN.search(line):
                    violations.append(f"{rel}:{number}: {line.strip()}")
    if violations:
        print("OWNER_BOUNDARY_VIOLATIONS")
        for item in violations:
            print(item)
        return 1
    print("OWNER_BOUNDARY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
