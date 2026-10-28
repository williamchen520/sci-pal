"""Build Chroma embeddings for section summaries (RAPTOR-lite vector channel)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
CHROMA = Path(__file__).resolve().parent.parent / "data" / "chroma"
MODEL = os.environ.get(
    "SCIPAL_EMBEDDING_MODEL", r"D:\models\models\BAAI--bge-base-en-v1.5"
)


def build(limit: int = 0, batch_size: int = 512) -> dict:
    model = SentenceTransformer(MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA))
    collection = client.get_or_create_collection(
        name="section_summaries", metadata={"hnsw:space": "cosine"}
    )
    conn = sqlite3.connect(str(DB))
    query = (
        "SELECT summary_id, paper_id, section_id, title, text FROM summaries "
        "ORDER BY summary_id"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()

    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        texts = [row[4] or "" for row in batch]
        embeddings = model.encode(
            texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True
        )
        collection.upsert(
            ids=[row[0] for row in batch],
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=[
                {"paper_id": row[1], "section_id": row[2], "title": row[3] or ""}
                for row in batch
            ],
        )
        total += len(batch)
        print(f"{total}/{len(rows)}")
    return {"indexed": total, "collection": "section_summaries"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    print(build(args.limit))
