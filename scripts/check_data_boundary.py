#!/usr/bin/env python3
"""Assert physical data decoupling between scipal_core and scipal_rebuild."""
from __future__ import annotations

import os
import sys

import psycopg

CORPUS_TABLES = {
    "papers", "paragraphs", "sentences", "sections", "paragraph_embeddings",
    "citations", "figures", "tables", "summaries", "sentence_links",
    "paper_links", "citation_network", "fts_term_stats",
}
CORE_TABLES = {
    "users", "workspaces", "memberships", "projects", "experiments", "notes",
    "tasks", "tenancy_audit",
}


def tables(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as conn:
        return {
            row[0]
            for row in conn.execute(
                "select table_name from information_schema.tables "
                "where table_schema='public' and table_type='BASE TABLE'"
            )
        }


def main() -> int:
    core = os.environ.get("SCIPAL_CORE_DSN", "").strip()
    corpus = os.environ.get("SCIPAL_PG_CORPUS_DSN", "").strip()
    if not core or not corpus:
        raise SystemExit("SCIPAL_CORE_DSN and SCIPAL_PG_CORPUS_DSN are required")
    core_tables = tables(core)
    corpus_tables = tables(corpus)
    errors = []
    warnings = []
    leaked_corpus = core_tables & CORPUS_TABLES
    leaked_core = corpus_tables & CORE_TABLES
    if leaked_corpus:
        errors.append(f"core contains corpus tables: {sorted(leaked_corpus)}")
    for table in sorted(leaked_core):
        with psycopg.connect(corpus) as conn:
            count = conn.execute(f"select count(*) from public.{table}").fetchone()[0]
        if count:
            errors.append(f"corpus contains non-empty core table: {table} ({count})")
        else:
            warnings.append(f"corpus contains empty core shell: {table}")
    if errors:
        print("DATA_BOUNDARY_FAILED")
        for error in errors:
            print(error)
        return 1
    for warning in warnings:
        print(f"WARN {warning}")
    print("DATA_BOUNDARY_OK")
    print(f"core_tables={len(core_tables)} corpus_tables={len(corpus_tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
