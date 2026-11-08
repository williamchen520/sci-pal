"""Fail when a new sqlite3.connect appears outside the frozen allowlist."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "sqlite_connect_allowlist.txt"
PATTERN = re.compile(r"sqlite3\.connect\(")


def scan() -> set[str]:
    found: set[str] = set()
    for base in ("services", "routes"):
        for path in (ROOT / base).rglob("*.py"):
            if PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")):
                found.add(path.relative_to(ROOT).as_posix())
    if PATTERN.search((ROOT / "api_server.py").read_text(encoding="utf-8")):
        found.add("api_server.py")
    return found


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        return set()
    return {
        line.strip()
        for line in ALLOWLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="freeze current files")
    args = parser.parse_args()
    found = scan()
    if args.update:
        ALLOWLIST.write_text("\n".join(sorted(found)) + "\n", encoding="utf-8")
        print(f"SQLITE_ALLOWLIST_UPDATED {len(found)}")
        return 0
    allowed = load_allowlist()
    new = sorted(found - allowed)
    removed = sorted(allowed - found)
    if new:
        print("SQLITE_NEW_CONNECTIONS")
        for item in new:
            print(item)
        return 1
    if removed:
        print("SQLITE_ALLOWLIST_STALE")
        for item in removed:
            print(item)
        print("run: python scripts/audit_sqlite.py --update")
        return 1
    print(f"SQLITE_ALLOWLIST_OK {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
