#!/usr/bin/env python3
"""Backfill paper_sources without reparsing the corpus."""

from __future__ import annotations

import argparse
import os

import psycopg

JATS_SQL = """
INSERT INTO paper_sources
  (source_id, paper_id, source_kind, source_uri, parser, parser_version, is_primary, metadata)
SELECT
  'src_' || substr(md5(p.paper_id || ':jats'), 1, 16),
  p.paper_id,
  'jats',
  'documents_xml/' || p.filename,
  'jats',
  'xml',
  true,
  jsonb_build_object('pmcid', split_part(p.filename, '.', 1))
FROM papers p
WHERE p.filename IS NOT NULL
  AND p.filename <> ''
  AND p.paper_id LIKE 'paper_PMC%'
ON CONFLICT DO NOTHING
"""

PDF_ROWS = (
    (
        "paper_nature_hcc_lipid_macrophage_b3cb651d2d57",
        "documents/nature_hcc_lipid_macrophage.pdf",
    ),
    (
        "paper_hcc_genomic_4492073cf016",
        "documents/hcc_genomic.pdf",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        xml = conn.execute(JATS_SQL).rowcount
        pdf = 0
        for paper_id, uri in PDF_ROWS:
            exists = conn.execute(
                "SELECT 1 FROM papers WHERE paper_id=%s", (paper_id,)
            ).fetchone()
            if not exists:
                continue
            conn.execute(
                """
                INSERT INTO paper_sources
                  (source_id, paper_id, source_kind, source_uri, parser, parser_version,
                   is_primary, metadata)
                VALUES (%s,%s,'pdf',%s,'docling','1',true,'{}'::jsonb)
                ON CONFLICT DO NOTHING
                """,
                (
                    "src_" + __import__("hashlib").md5(f"{paper_id}:pdf".encode()).hexdigest()[:16],
                    paper_id,
                    uri,
                ),
            )
            pdf += 1
        conn.commit()
        total = conn.execute("SELECT count(*) FROM paper_sources").fetchone()[0]
    print(f"PAPER_SOURCES_OK xml={xml} pdf={pdf} total={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
