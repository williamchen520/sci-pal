"""Build paragraph embeddings directly into PostgreSQL/pgvector."""

from __future__ import annotations

import argparse
import os

from sentence_transformers import SentenceTransformer

from services.db.pg_pool import pg_connection

MODEL = os.environ.get("SCIPAL_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")


def _device() -> str:
    requested = os.environ.get("SCIPAL_EMBEDDING_DEVICE", "").strip().lower()
    if requested:
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


def build(limit: int = 0, batch_size: int = 128, model_name: str = "") -> dict:
    device = _device()
    model = SentenceTransformer(model_name or MODEL, device=device)
    print(f"embedding device: {device}", flush=True)
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT para_id, paper_id, text FROM paragraphs "
            "WHERE text IS NOT NULL AND length(btrim(text)) >= 10 "
            "ORDER BY paper_id, sequence"
        ).fetchall()
        if limit:
            rows = rows[:limit]
        existing = {
            row["para_id"] for row in pg.execute("SELECT para_id FROM paragraph_embeddings")
        }
        pending = [row for row in rows if row["para_id"] not in existing]
        inserted = 0
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            texts = [row["text"] for row in batch]
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            with pg.cursor() as cur:
                cur.executemany(
                    "INSERT INTO paragraph_embeddings (para_id,paper_id,embedding) "
                    "VALUES (%s,%s,%s::vector) ON CONFLICT (para_id) DO NOTHING",
                    [
                        (row["para_id"], row["paper_id"], "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]")
                        for row, vec in zip(batch, vectors)
                    ],
                )
            pg.commit()
            inserted += len(batch)
        return {"candidates": len(rows), "inserted": inserted, "existing": len(existing)}
    finally:
        pg.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch", type=int, default=128)
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    print(build(args.limit, args.batch, args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
