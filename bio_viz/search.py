"""Hybrid search over the independent BioViz recipe database."""

from __future__ import annotations

import argparse
import json
import os

import psycopg
from sentence_transformers import SentenceTransformer

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")


def search(query: str, *, top_k: int = 5, dsn: str | None = None, model=None) -> list[dict]:
    dsn = dsn or os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    model = model or SentenceTransformer(MODEL, device=os.environ.get("SCIPAL_CODE_DEVICE", "cuda"))
    vector = json.dumps(model.encode([query], normalize_embeddings=True)[0].tolist())
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            """
            WITH vec AS (
              SELECT r.recipe_id, row_number() OVER (ORDER BY e.embedding <=> %s::vector) AS rnk
              FROM code_rag.embeddings e
              JOIN code_rag.recipes r ON r.recipe_id = e.recipe_id
              ORDER BY e.embedding <=> %s::vector
              LIMIT 20
            ),
            lex AS (
              SELECT recipe_id, row_number() OVER (ORDER BY similarity(title || ' ' || intent, %s) DESC) AS rnk
              FROM code_rag.recipes
              WHERE similarity(title || ' ' || intent, %s) > 0.02
              ORDER BY similarity(title || ' ' || intent, %s) DESC
              LIMIT 20
            ),
            fused AS (
              SELECT recipe_id, 1.0 / (60 + rnk) AS score FROM vec
              UNION ALL
              SELECT recipe_id, 1.0 / (60 + rnk) AS score FROM lex
            )
            SELECT r.recipe_id, r.title, r.chart_type, r.intent, r.data_schema,
                   r.code, r.packages, r.style_id, r.source, r.license,
                   SUM(f.score) AS score
            FROM fused f
            JOIN code_rag.recipes r ON r.recipe_id = f.recipe_id
            GROUP BY r.recipe_id, r.title, r.chart_type, r.intent, r.data_schema,
                     r.code, r.packages, r.style_id, r.source, r.license
            ORDER BY score DESC
            LIMIT %s
            """,
            (vector, vector, query, query, query, top_k),
        ).fetchall()
    return [
        {
            "recipe_id": row[0],
            "title": row[1],
            "chart_type": row[2],
            "intent": row[3],
            "data_schema": row[4],
            "code": row[5],
            "packages": row[6],
            "style_id": row[7],
            "source": row[8],
            "license": row[9],
            "score": float(row[10]),
        }
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    hits = search(args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(hits, ensure_ascii=False, indent=2))
    else:
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit['title']} [{hit['chart_type']}] style={hit['style_id']} score={hit['score']:.4f}")
            print(f"   {hit['intent']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
