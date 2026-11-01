#!/usr/bin/env python3
"""Create the empty scipal_v2 database and apply schema v2.

P1 only: no data migration, no writes to the production database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.etl import quote_ident  # noqa: E402

SCHEMA = ROOT / "build_db" / "postgres_schema_v2.sql"
REQUIRED_TABLES = (
    "papers",
    "documents",
    "source_nodes",
    "sections",
    "paragraphs",
    "sentences",
    "figures",
    "tables",
    "pdf_pages",
    "pdf_blocks",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-admin-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--db", default="scipal_v2")
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_admin_dsn:
        raise SystemExit("SCIPAL_PG_DSN or --pg-admin-dsn is required")
    if args.db != "scipal_v2" and not args.db.endswith("_v2"):
        raise SystemExit("refusing to create a non-v2 database")

    from psycopg import conninfo
    import psycopg

    params = conninfo.conninfo_to_dict(args.pg_admin_dsn)
    params["dbname"] = "postgres"
    admin = conninfo.make_conninfo(**params)
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (args.db,)
        ).fetchone()
        if exists and args.recreate:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (args.db,),
            )
            conn.execute(f"DROP DATABASE {quote_ident(args.db)}")
        elif exists:
            raise SystemExit(f"database already exists: {args.db}; use --recreate")
        conn.execute(f"CREATE DATABASE {quote_ident(args.db)}")

    params["dbname"] = args.db
    dsn = conninfo.make_conninfo(**params)
    schema_sql = SCHEMA.read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        conn.execute(schema_sql)
        conn.commit()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public'"
            )
        }
        missing = [name for name in REQUIRED_TABLES if name not in tables]
        columns = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public'"
            )
        }
    report = {
        "database": args.db,
        "tables": sorted(tables),
        "missing_tables": missing,
        "has_sentence_fts": ("sentences", "search_vector") in columns,
        "has_figure_binding": ("figures", "section_id") in columns,
        "has_pdf_bbox": ("pdf_blocks", "bbox") in columns,
        "status": "ok" if not missing else "degraded",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
