#!/usr/bin/env python3
"""Import a publisher HTML file into the native HTML source store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.html_parser import parse_html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")

    raw = Path(args.file).read_bytes()
    parsed = parse_html(raw, source_url=args.source_url)
    digest = parsed["content_hash"]
    source_id = "src_" + hashlib.md5(
        f"{args.paper_id}:html:{digest}".encode()
    ).hexdigest()[:16]

    with psycopg.connect(args.dsn) as conn:
        conn.execute(
            """
            INSERT INTO paper_sources
              (source_id, paper_id, source_kind, source_uri, content_hash,
               parser, parser_version, is_primary, metadata)
            VALUES (%s,%s,'html',%s,%s,'html_parser','v1',false,%s::jsonb)
            ON CONFLICT (paper_id, source_kind, source_uri) DO UPDATE SET
              content_hash=EXCLUDED.content_hash,
              metadata=EXCLUDED.metadata
            """,
            (
                source_id,
                args.paper_id,
                args.source_url,
                digest,
                json.dumps({"doi": parsed["doi"]}, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "SELECT source_id FROM paper_sources "
            "WHERE paper_id=%s AND source_kind='html' AND source_uri=%s",
            (args.paper_id, args.source_url),
        ).fetchone()
        source_id = row[0]

        conn.execute(
            """
            INSERT INTO html_articles
              (source_id, paper_id, source_url, content_hash, title, doi,
               journal, published, license, native_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (source_id) DO UPDATE SET
              title=EXCLUDED.title,
              doi=EXCLUDED.doi,
              journal=EXCLUDED.journal,
              published=EXCLUDED.published,
              license=EXCLUDED.license,
              native_json=EXCLUDED.native_json
            """,
            (
                source_id,
                args.paper_id,
                parsed["source_url"],
                digest,
                parsed["title"],
                parsed["doi"],
                parsed["journal"],
                parsed["published"],
                parsed["license"],
                json.dumps(
                    {
                        "figures": parsed["figures"],
                        "code_links": parsed["code_links"],
                        "data_links": parsed["data_links"],
                        "warnings": parsed["warnings"],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute("DELETE FROM html_paragraphs WHERE source_id=%s", (source_id,))
        conn.execute("DELETE FROM html_sections WHERE source_id=%s", (source_id,))
        para_count = 0
        for s_index, section in enumerate(parsed["sections"], start=1):
            section_id = f"hsec_{s_index:03d}"
            conn.execute(
                "INSERT INTO html_sections (source_id, native_section_id, title, section_order) "
                "VALUES (%s,%s,%s,%s)",
                (source_id, section_id, section["title"], s_index),
            )
            for p_index, text in enumerate(section["paragraphs"], start=1):
                para_count += 1
                conn.execute(
                    "INSERT INTO html_paragraphs "
                    "(source_id, native_para_id, section_id, text, para_order) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (source_id, f"hpara_{s_index:03d}_{p_index:03d}", section_id, text, p_index),
                )
        conn.commit()
    print(
        f"HTML_SOURCE_OK paper={args.paper_id} source={source_id} "
        f"sections={len(parsed['sections'])} paragraphs={para_count} hash={digest[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
