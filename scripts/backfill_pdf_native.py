#!/usr/bin/env python3
"""Backfill PDF native page/bbox from canonical paragraphs."""

from __future__ import annotations

import argparse
import os

import psycopg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        sources = conn.execute(
            "SELECT source_id,paper_id,source_uri,content_hash,parser "
            "FROM paper_sources WHERE source_kind='pdf'"
        ).fetchall()
        paragraphs_written = 0
        for source_id, paper_id, source_uri, content_hash, parser_name in sources:
            pages = conn.execute(
                "SELECT max(page) AS max_page FROM paragraphs WHERE paper_id=%s",
                (paper_id,),
            ).fetchone()[0] or 0
            conn.execute(
                """
                INSERT INTO pdf_documents
                  (source_id, paper_id, source_uri, content_hash, parser, page_count)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_id) DO UPDATE SET
                  page_count=EXCLUDED.page_count,
                  parser=EXCLUDED.parser
                """,
                (source_id, paper_id, source_uri, content_hash, parser_name, pages),
            )
            conn.execute("DELETE FROM pdf_paragraphs WHERE source_id=%s", (source_id,))
            rows = conn.execute(
                "SELECT para_id,page,bbox,text,sequence FROM paragraphs "
                "WHERE paper_id=%s ORDER BY sequence",
                (paper_id,),
            ).fetchall()
            for para_id, page, bbox, text, sequence in rows:
                conn.execute(
                    """
                    INSERT INTO pdf_paragraphs
                      (source_id, native_para_id, para_id, page, bbox, text, para_order)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        source_id,
                        para_id,
                        para_id,
                        page,
                        bbox,
                        text or "",
                        sequence,
                    ),
                )
                paragraphs_written += 1
            conn.commit()
    print(
        f"PDF_NATIVE_OK sources={len(sources)} paragraphs={paragraphs_written}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
