"""Build code-unit embeddings in scipal_code (P3)."""

from __future__ import annotations

import argparse
import json
import os

import psycopg
from sentence_transformers import SentenceTransformer

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")
SKIP_TYPES = ("file",)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--device", default=os.environ.get("SCIPAL_CODE_DEVICE", "cuda"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")

    model = SentenceTransformer(args.model, device=args.device)
    with psycopg.connect(args.dsn) as conn:
        params = [args.library_id]
        where = "library_id=%s AND unit_type <> 'file'"
        if args.snapshot_id:
            where += " AND snapshot_id=%s"
            params.append(args.snapshot_id)
        rows = conn.execute(
            f"SELECT unit_id, symbol_name, text FROM code_rag.code_units WHERE {where} ORDER BY unit_id",
            tuple(params),
        ).fetchall()
        run = conn.execute(
            "INSERT INTO code_rag.code_ingest_runs (library_id,snapshot_id,status) "
            "VALUES (%s,%s,'running') RETURNING run_id",
            (args.library_id, args.snapshot_id),
        ).fetchone()[0]
        vectors = model.encode(
            [f"{row[1]}\n{row[2][:4000]}" for row in rows],
            batch_size=args.batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        for row, vector in zip(rows, vectors):
            conn.execute(
                """
                INSERT INTO code_rag.code_embeddings (unit_id, library_id, model, embedding)
                VALUES (%s,%s,%s,%s::vector)
                ON CONFLICT (unit_id) DO UPDATE SET
                  embedding=EXCLUDED.embedding, model=EXCLUDED.model
                """,
                (row[0], args.library_id, args.model, json.dumps(vector.tolist())),
            )
        conn.execute(
            "UPDATE code_rag.code_ingest_runs SET status='completed', units=%s, finished_at=now() "
            "WHERE run_id=%s",
            (len(rows), run),
        )
        conn.commit()
    print(f"CODE_RAG_INDEX_OK units={len(rows)} library={args.library_id} dim={model.get_embedding_dimension()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
