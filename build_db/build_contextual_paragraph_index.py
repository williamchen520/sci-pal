"""Build a contextual paragraph vector index.

Each paragraph is embedded with its document/section context:

    paper title > section path > paragraph text

Collection: ``paragraphs_contextual`` (query it with
``SCIPAL_PARAGRAPH_COLLECTION=paragraphs_contextual``).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
CHROMA = Path(__file__).resolve().parent.parent / "data" / "chroma"
MODEL = os.environ.get(
    "SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5"
)
COLLECTION = "paragraphs_contextual"


def contextual_text(title: str, section_path: str, text: str) -> str:
    prefix = " > ".join(part for part in (title, section_path) if part)
    return f"{prefix}. {text}" if prefix else text


def build(limit: int = 0, batch_size: int = 512) -> dict:
    model = SentenceTransformer(MODEL)
    client = chromadb.PersistentClient(path=str(CHROMA))
    collection = client.get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    query = (
        "SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2, "
        "p.section_path, p.text, pa.title "
        "FROM paragraphs p LEFT JOIN papers pa ON pa.paper_id = p.paper_id "
        "WHERE p.text IS NOT NULL AND length(p.text) > 20 ORDER BY p.para_id"
    )
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    existing_ids = set(collection.get(include=[]).get("ids") or [])
    rows = [row for row in rows if row["para_id"] not in existing_ids]
    print(f"skip existing {len(existing_ids)}, remaining {len(rows)}", flush=True)

    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        documents = [
            contextual_text(
                row["title"] or "",
                row["section_path"] or row["section_level2"] or row["section_level1"] or "",
                row["text"] or "",
            )
            for row in batch
        ]
        embeddings = model.encode(
            documents, batch_size=256, show_progress_bar=False, normalize_embeddings=True
        )
        collection.upsert(
            ids=[row["para_id"] for row in batch],
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=[
                {
                    "paper_id": row["paper_id"] or "",
                    "section_l1": row["section_level1"] or "",
                    "section_l2": row["section_level2"] or "",
                }
                for row in batch
            ],
        )
        total += len(batch)
        print(f"{total}/{len(rows)}", flush=True)
    return {"indexed": total, "collection": COLLECTION}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    print(build(args.limit))
