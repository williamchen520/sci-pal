#!/usr/bin/env python3
"""G4b: backfill Chroma paragraph embeddings into production PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import chromadb
import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import CHROMA_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_DSN required")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection("paragraphs")
    total = collection.count()
    stop = min(total, args.limit) if args.limit else total
    print(f"chroma {total}, backfill {stop}", flush=True)

    pg = psycopg.connect(args.dsn)
    pg.autocommit = False
    done = 0
    try:
        for offset in range(0, stop, args.batch):
            size = min(args.batch, stop - offset)
            got = collection.get(
                limit=size,
                offset=offset,
                include=["embeddings", "metadatas"],
            )
            ids = got.get("ids") or []
            embeddings = got.get("embeddings")
            metas = got.get("metadatas") or []
            if embeddings is None or len(ids) == 0:
                break
            rows = []
            for index, para_id in enumerate(ids):
                meta = metas[index] or {}
                paper_id = meta.get("paper_id")
                if not paper_id:
                    row = pg.execute(
                        "SELECT paper_id FROM paragraphs WHERE para_id=%s", (para_id,)
                    ).fetchone()
                    paper_id = row[0] if row else ""
                if not paper_id:
                    continue
                vector = "[" + ",".join(f"{float(v):.6f}" for v in embeddings[index]) + "]"
                rows.append((para_id, paper_id, vector))
            if rows:
                with pg.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO paragraph_embeddings (para_id, paper_id, embedding) "
                        "VALUES (%s, %s, %s::vector) "
                        "ON CONFLICT (para_id) DO UPDATE SET "
                        "paper_id=EXCLUDED.paper_id, embedding=EXCLUDED.embedding, "
                        "updated_at=now()",
                        rows,
                    )
                pg.commit()
            done += len(rows)
            print(f"{done}/{stop}", flush=True)
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
