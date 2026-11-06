#!/usr/bin/env python3
"""G4b1: audit Chroma vs PostgreSQL corpus parity (direct SQLite read)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import CHROMA_PATH  # noqa: E402


def _hash(text: str) -> str:
    return hashlib.sha256(" ".join((text or "").split()).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--out", default="eval/results/g4_corpus_audit.json")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_DSN required")

    chroma_db = Path(CHROMA_PATH) / "chroma.sqlite3"
    c = sqlite3.connect(f"file:{chroma_db}?mode=ro", uri=True)
    collection = c.execute(
        "SELECT id FROM collections WHERE name='paragraphs'"
    ).fetchone()
    if not collection:
        raise SystemExit("paragraphs collection not found")
    segment = c.execute(
        "SELECT id FROM segments WHERE collection=? AND scope='METADATA'",
        (collection[0],),
    ).fetchone()
    if not segment:
        raise SystemExit("metadata segment not found")
    rows = c.execute(
        "SELECT e.embedding_id, m1.string_value, m2.string_value "
        "FROM embeddings e "
        "JOIN embedding_metadata m1 ON m1.id=e.id AND m1.key='paper_id' "
        "LEFT JOIN embedding_metadata m2 ON m2.id=e.id AND m2.key='chroma:document' "
        "WHERE e.segment_id=?",
        (segment[0],),
    ).fetchall()
    c.close()
    print(f"chroma {len(rows)}", flush=True)

    chroma_ids: set[str] = set()
    chroma_paper: dict[str, str] = {}
    chroma_counts: Counter[str] = Counter()
    docs: dict[str, str] = {}
    missing_meta = 0
    dup_ids = 0
    for para_id, paper_id, document in rows:
        if para_id in chroma_ids:
            dup_ids += 1
            continue
        chroma_ids.add(para_id)
        if not paper_id:
            missing_meta += 1
        else:
            chroma_paper[para_id] = paper_id
            chroma_counts[paper_id] += 1
        docs[para_id] = document or ""

    pg = psycopg.connect(args.dsn)
    pg_rows = pg.execute("SELECT para_id, paper_id, text FROM paragraphs").fetchall()
    pg_ids = {row[0] for row in pg_rows}
    pg_paper = {row[0]: row[1] for row in pg_rows}
    pg_text = {row[0]: row[2] or "" for row in pg_rows}
    pg_counts = Counter(row[1] for row in pg_rows if row[1])
    print(f"pg {len(pg_rows)}", flush=True)

    missing_in_pg = sorted(chroma_ids - pg_ids)
    extra_in_pg = sorted(pg_ids - chroma_ids)
    paper_mismatch = [
        pid for pid in (chroma_ids & pg_ids)
        if chroma_paper.get(pid) and pg_paper.get(pid) != chroma_paper.get(pid)
    ]
    text_mismatch = [
        pid for pid in list(docs)[:5000]
        if pid in pg_text and _hash(docs[pid]) != _hash(pg_text[pid])
    ]

    orphan_emb = pg.execute(
        "SELECT count(*) FROM paragraph_embeddings e "
        "LEFT JOIN paragraphs p ON p.para_id=e.para_id WHERE p.para_id IS NULL"
    ).fetchone()[0]
    no_emb = pg.execute(
        "SELECT count(*) FROM paragraphs p "
        "LEFT JOIN paragraph_embeddings e ON e.para_id=p.para_id WHERE e.para_id IS NULL"
    ).fetchone()[0]
    count_diffs = {
        paper: [chroma_counts.get(paper, 0), pg_counts.get(paper, 0)]
        for paper in set(chroma_counts) | set(pg_counts)
        if chroma_counts.get(paper, 0) != pg_counts.get(paper, 0)
    }

    report = {
        "chroma_total": len(rows),
        "pg_total": len(pg_rows),
        "chroma_unique_ids": len(chroma_ids),
        "duplicate_chroma_ids": dup_ids,
        "missing_metadata_paper_id": missing_meta,
        "missing_in_pg": len(missing_in_pg),
        "extra_in_pg": len(extra_in_pg),
        "missing_in_pg_sample": missing_in_pg[:20],
        "extra_in_pg_sample": extra_in_pg[:20],
        "paper_id_mismatch": len(paper_mismatch),
        "paper_id_mismatch_sample": paper_mismatch[:20],
        "text_checked": len([p for p in list(docs)[:5000] if p in pg_text]),
        "text_mismatch": len(text_mismatch),
        "text_mismatch_sample": text_mismatch[:20],
        "orphan_embeddings": orphan_emb,
        "paragraphs_without_embedding": no_emb,
        "paper_count_diff_count": len(count_diffs),
        "paper_count_diff_sample": dict(list(count_diffs.items())[:20]),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
