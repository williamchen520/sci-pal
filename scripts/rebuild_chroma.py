"""Build a fresh Chroma collection from the paragraphs table.

Why: HNSW segment files are append-only; deleting vectors leaves tombstones and
the index keeps its size. Rebuilding into a *new* directory (then swapping) frees
the space without touching the live index until the final switch.

Usage::

    python scripts/rebuild_chroma.py --target data/chroma_rebuild --limit 300   # smoke
    python scripts/rebuild_chroma.py --target data/chroma_rebuild               # full

Swap (services stopped)::

    data/chroma -> data/chroma_old ; data/chroma_rebuild -> data/chroma
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "research.db"
MODEL = Path(r"D:\models\models\BAAI--bge-base-en-v1.5")
COLLECTION = "paragraphs"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--batch", type=int, default=512, help="outer batch (512 measured ~2x faster than 32)")
    parser.add_argument("--limit", type=int, default=0, help="0 = all paragraphs")
    parser.add_argument("--device", default="cuda", help="cpu or cuda (cuda ~150 eps)")
    parser.add_argument("--ef-construction", type=int, default=100, help="HNSW construction_ef")
    parser.add_argument("--m", type=int, default=16, help="HNSW M")
    args = parser.parse_args()

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    sql = "SELECT para_id, paper_id, section_level1, text FROM paragraphs"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = conn.execute(sql).fetchall()
    conn.close()
    print(f"paragraphs to embed: {len(rows)} -> {target}", flush=True)

    model = SentenceTransformer(str(MODEL), device=args.device)
    client = chromadb.PersistentClient(path=str(target))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": int(args.ef_construction),
            "hnsw:M": int(args.m),
        },
    )

    started = time.time()
    for start in range(0, len(rows), args.batch):
        chunk = rows[start:start + args.batch]
        ids = [row["para_id"] for row in chunk]
        documents = [row["text"] or "" for row in chunk]
        metadatas = [
            {
                "paper_id": row["paper_id"] or "",
                "section_l1": row["section_level1"] or "",
                "section_l2": "",
            }
            for row in chunk
        ]
        embeddings = model.encode(documents, show_progress_bar=False).tolist()
        collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        done = min(start + args.batch, len(rows))
        elapsed = max(time.time() - started, 0.001)
        print(f"embedded {done}/{len(rows)} ({done / elapsed:.1f}/s)", flush=True)

    count = collection.count()
    print(f"done: {count} vectors in {target}", flush=True)
    return 0 if count == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
