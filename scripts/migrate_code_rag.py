#!/usr/bin/env python3
"""Apply the code_rag schema to the independent scipal_code database."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

SCHEMA = Path(__file__).resolve().parent.parent / "code_rag" / "schema.sql"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    statements = [
        part.strip() for part in SCHEMA.read_text(encoding="utf-8").split(";") if part.strip()
    ]
    with psycopg.connect(args.dsn) as conn:
        with conn.transaction():
            for statement in statements:
                conn.execute(statement)
    print(f"CODE_RAG_MIGRATION_OK statements={len(statements)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
