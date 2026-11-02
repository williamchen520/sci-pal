#!/usr/bin/env python3
"""Apply a simple PG migration file, one statement at a time."""

from __future__ import annotations

import argparse
from pathlib import Path

SKIP = {"BEGIN", "COMMIT"}


def statements(sql: str) -> list[str]:
    out = []
    for raw in sql.split(";"):
        statement = raw.strip()
        if not statement or statement.upper() in SKIP:
            continue
        out.append(statement)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", required=True)
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    parts = statements(Path(args.sql).read_text(encoding="utf-8"))
    print(f"statements={len(parts)} apply={args.apply}")
    if not args.apply:
        for part in parts:
            print(part.splitlines()[0])
        return 0
    import psycopg

    with psycopg.connect(args.pg_dsn) as pg:
        for part in parts:
            pg.execute(part)
        pg.commit()
    print("applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
