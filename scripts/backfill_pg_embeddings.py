"""Backfill paragraph embeddings from Chroma into PostgreSQL pgvector."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
import psycopg

from config.paths import CHROMA_PATH


def vector_literal(values) -> str:
    return "[" + ",".join(f"{float(value):.6f}" for value in values) + "]"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", default="paragraphs_contextual")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PARADEDB_DSN", ""))
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--truncate", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PARADEDB_DSN or --dsn is required")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(args.collection)
    total = collection.count() if not args.limit else min(collection.count(), args.limit)
    print(f"source={args.collection} total={total}", flush=True)

    conn = psycopg.connect(args.dsn)
    inserted = 0
    try:
        with conn.cursor() as cur:
            if args.truncate:
                cur.execute("TRUNCATE paragraph_embeddings")
                conn.commit()
            for offset in range(0, total, args.batch):
                batch = collection.get(
                    limit=min(args.batch, total - offset),
                    offset=offset,
                    include=["embeddings", "metadatas"],
                )
                ids = batch.get("ids") or []
                embeddings = batch.get("embeddings")
                if embeddings is None:
                    embeddings = []
                metadatas = batch.get("metadatas") or []
                rows = []
                for index, para_id in enumerate(ids):
                    meta = metadatas[index] if index < len(metadatas) else {}
                    paper_id = (meta or {}).get("paper_id") or ""
                    if not paper_id:
                        continue
                    rows.append(
                        (para_id, paper_id, vector_literal(embeddings[index]), "bge-base-en-v1.5")
                    )
                if rows:
                    if args.truncate:
                        with cur.copy(
                            "COPY paragraph_embeddings "
                            "(para_id, paper_id, embedding, model) FROM STDIN"
                        ) as copy:
                            for row in rows:
                                copy.write_row(row)
                    else:
                        cur.executemany(
                            "INSERT INTO paragraph_embeddings "
                            "(para_id, paper_id, embedding, model) VALUES (%s, %s, %s::vector, %s) "
                            "ON CONFLICT (para_id) DO UPDATE SET "
                            "paper_id=EXCLUDED.paper_id, embedding=EXCLUDED.embedding, "
                            "model=EXCLUDED.model, updated_at=now()",
                            rows,
                        )
                    conn.commit()
                    inserted += len(rows)
                print(f"offset={offset} inserted={inserted}", flush=True)
    finally:
        conn.close()
    print(f"done inserted={inserted}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
