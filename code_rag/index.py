"""Build code-unit embeddings in scipal_code (P3)."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import psycopg
from sentence_transformers import SentenceTransformer

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")
SKIP_TYPES = ("file",)


def index_library(
    dsn: str,
    library_id: str,
    snapshot_id: str = "",
    *,
    model_name: str = "",
    device: str = "",
    batch_size: int = 32,
) -> dict[str, Any]:
    """Embed code units for a library/snapshot and record an ingest run."""
    if not dsn:
        raise ValueError("SCIPAL_CODE_DSN is required")
    model_name = model_name or MODEL
    device = device or os.environ.get("SCIPAL_CODE_DEVICE", "cuda")
    model = SentenceTransformer(model_name, device=device)
    with psycopg.connect(dsn) as conn:
        params = [library_id]
        where = "library_id=%s AND unit_type <> 'file'"
        if snapshot_id:
            where += " AND snapshot_id=%s"
            params.append(snapshot_id)
        rows = conn.execute(
            f"SELECT unit_id, symbol_name, text FROM code_rag.code_units WHERE {where} ORDER BY unit_id",
            tuple(params),
        ).fetchall()
        run = conn.execute(
            "INSERT INTO code_rag.code_ingest_runs (library_id,snapshot_id,status) "
            "VALUES (%s,%s,'running') RETURNING run_id",
            (library_id, snapshot_id),
        ).fetchone()[0]
        vectors = model.encode(
            [f"{row[1]}\n{row[2][:4000]}" for row in rows],
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        for row, vector in zip(rows, vectors):
            conn.execute(
                """
                INSERT INTO code_rag.code_embeddings (unit_id, library_id, model, embedding)
                VALUES (%s,%s,%s,%s::vector)
                ON CONFLICT (unit_id) DO UPDATE SET
                  embedding=EXCLUDED.embedding, model=EXCLUDED.model
                """,
                (row[0], library_id, model_name, json.dumps(vector.tolist())),
            )
        conn.execute(
            "UPDATE code_rag.code_ingest_runs SET status='completed', units=%s, finished_at=now() "
            "WHERE run_id=%s",
            (len(rows), run),
        )
        conn.commit()
    return {
        "run_id": run,
        "units": len(rows),
        "library_id": library_id,
        "snapshot_id": snapshot_id,
        "model": model_name,
        "dim": model.get_embedding_dimension(),
    }


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
    result = index_library(
        args.dsn,
        args.library_id,
        args.snapshot_id,
        model_name=args.model,
        device=args.device,
        batch_size=args.batch_size,
    )
    print(
        f"CODE_RAG_INDEX_OK units={result['units']} library={args.library_id} "
        f"dim={result['dim']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
