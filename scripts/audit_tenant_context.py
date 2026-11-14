#!/usr/bin/env python3
"""Audit tenant-context boundaries.

Strict mode fails if tenancy/federation code reads global SCIPAL_PG_* values
outside ``context.py``.  It also reports direct corpus_connection() usages as
migration debt; those are not failed in S0.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

STRICT_DIRS = ("services/tenancy", "services/federation")
LEGACY_ALLOWLIST = {"services/tenancy/pg_writes.py"}
DSN_RE = re.compile(r"SCIPAL_PG_[A-Z_]+|SCIPAL_CORE_DSN|SCIPAL_CODE_READ_DSN")
GLOBAL_CONN_RE = re.compile(r"\bcorpus_connection\s*\(")


def _files(root: Path, rel_dir: str):
    base = root / rel_dir
    if not base.exists():
        return []
    return sorted(base.rglob("*.py"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    violations: list[str] = []
    legacy: list[str] = []
    global_uses: list[str] = []
    for rel_dir in STRICT_DIRS:
        for path in _files(root, rel_dir):
            if path.name == "context.py":
                continue
            if path.relative_to(root).as_posix() in LEGACY_ALLOWLIST:
                legacy.append(path.relative_to(root).as_posix())
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if DSN_RE.search(line) and "environ" in line:
                    violations.append(f"{path.relative_to(root)}:{line_no}: {line.strip()}")
    for rel_dir in ("services", "routes"):
        for path in _files(root, rel_dir):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if GLOBAL_CONN_RE.search(line):
                    global_uses.append(f"{path.relative_to(root)}:{line_no}")
    print(f"TENANT_CONTEXT_STRICT_VIOLATIONS {len(violations)}")
    for item in violations:
        print("  " + item)
    print(f"LEGACY_EXEMPT {len(legacy)}")
    for item in legacy:
        print("  " + item)
    print(f"GLOBAL_CORPUS_CONNECTION_USES {len(global_uses)}")
    if args.strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
