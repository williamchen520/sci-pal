#!/usr/bin/env python3
"""Audit and repair embedding inputs.

The failure mode this guards against: parser IDs or section numbers accidentally
being concatenated into the text that gets embedded. Raw paragraphs remain
untouched; only index rows are removed.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ingest_quality.paragraph_filter import index_skip_reason

ID_RE = re.compile(r"(para_|sent_|section_id|paper_)[A-Za-z0-9]")
BAD_SQL = """
    (
      p.text !~ '[A-Za-z]'
      OR (p.text ~* '^(https?://|doi:|www\\.)' AND length(p.text) < 120)
      OR p.section_level1 ~* '^(references|reference|acknowledg|funding|conflict|author contributions|keywords|abbreviations)$'
      OR p.text ~* '^(received|accepted|published|check for updates|article|open access)\\b'
    )
"""


def _counts(conn, paper_id: str) -> dict[str, int]:
    where = "WHERE p.paper_id = %s" if paper_id else ""
    params = (paper_id,) if paper_id else ()
    paragraphs = conn.execute(
        f"SELECT count(*) FROM paragraphs p {where}", params
    ).fetchone()[0]
    ids = conn.execute(
        f"SELECT count(*) FROM paragraphs p {where} "
        f"{'AND' if where else 'WHERE'} p.text ~ '(para_|sent_|section_id|paper_)[A-Za-z0-9]'",
        params,
    ).fetchone()[0]
    sentence_ids = conn.execute(
        f"SELECT count(*) FROM sentences s {where.replace('p.', 's.')} "
        f"{'AND' if where else 'WHERE'} s.text ~ '(para_|sent_|section_id|paper_)[A-Za-z0-9]'",
        params,
    ).fetchone()[0]
    bad = conn.execute(
        f"SELECT count(*) FROM paragraphs p {where} "
        f"{'AND' if where else 'WHERE'} {BAD_SQL}",
        params,
    ).fetchone()[0]
    return {
        "paragraphs": paragraphs,
        "id_like_paragraphs": ids,
        "id_like_sentences": sentence_ids,
        "bad_input_candidates": bad,
    }


def repair(conn, paper_id: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT para_id, text, section_level1, section_level2 "
        "FROM paragraphs WHERE paper_id=%s ORDER BY sequence",
        (paper_id,),
    ).fetchall()
    bad = [
        row[0]
        for row in rows
        if index_skip_reason(row[1] or "", row[2] or "", row[3] or "")
    ]
    if not bad:
        return {"removed_embeddings": 0, "removed_sentences": 0}
    emb = conn.execute(
        "DELETE FROM paragraph_embeddings WHERE para_id = ANY(%s)", (bad,)
    ).rowcount
    sen = conn.execute(
        "DELETE FROM sentences WHERE para_id = ANY(%s)", (bad,)
    ).rowcount
    conn.commit()
    return {"removed_embeddings": emb, "removed_sentences": sen}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", default="")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    with psycopg.connect(args.dsn) as conn:
        before = _counts(conn, args.paper_id)
        print("AUDIT", before)
        if args.fix:
            if not args.paper_id:
                raise SystemExit("--fix requires --paper-id")
            result = repair(conn, args.paper_id)
            print("REPAIRED", result)
            print("AFTER", _counts(conn, args.paper_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
