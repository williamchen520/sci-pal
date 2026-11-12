"""Seed the independent BioViz recipe database."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from sentence_transformers import SentenceTransformer

from bio_viz.seed_data import RECIPES, STYLES

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--device", default=os.environ.get("SCIPAL_CODE_DEVICE", "cuda"))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")

    model = SentenceTransformer(args.model, device=args.device)
    texts = [
        f"{r['title']}\n{r['intent']}\n{r['chart_type']}\n{r['data_schema']}\n{r['code']}"
        for r in RECIPES
    ]
    vectors = model.encode(texts, batch_size=8, normalize_embeddings=True, show_progress_bar=False)

    with psycopg.connect(args.dsn) as conn:
        for style in STYLES:
            conn.execute(
                """
                INSERT INTO code_rag.styles (style_id, name, spec)
                VALUES (%s,%s,%s::jsonb)
                ON CONFLICT (style_id) DO UPDATE SET name=EXCLUDED.name, spec=EXCLUDED.spec
                """,
                (style["style_id"], style["name"], json.dumps(style["spec"])),
            )
        run = conn.execute(
            "INSERT INTO code_rag.ingest_runs (model, status) VALUES (%s,'running') RETURNING run_id",
            (args.model,),
        ).fetchone()[0]
        for recipe, vector in zip(RECIPES, vectors):
            conn.execute(
                """
                INSERT INTO code_rag.recipes
                  (recipe_id, title, chart_type, intent, data_schema, code, packages, style_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (recipe_id) DO UPDATE SET
                  title=EXCLUDED.title, chart_type=EXCLUDED.chart_type,
                  intent=EXCLUDED.intent, data_schema=EXCLUDED.data_schema,
                  code=EXCLUDED.code, packages=EXCLUDED.packages, style_id=EXCLUDED.style_id
                """,
                (
                    recipe["recipe_id"],
                    recipe["title"],
                    recipe["chart_type"],
                    recipe["intent"],
                    recipe["data_schema"],
                    recipe["code"],
                    json.dumps(recipe["packages"]),
                    recipe["style_id"],
                ),
            )
            conn.execute(
                """
                INSERT INTO code_rag.embeddings (recipe_id, embedding, model)
                VALUES (%s,%s::vector,%s)
                ON CONFLICT (recipe_id) DO UPDATE SET
                  embedding=EXCLUDED.embedding, model=EXCLUDED.model
                """,
                (recipe["recipe_id"], json.dumps(vector.tolist()), args.model),
            )
        conn.execute(
            "UPDATE code_rag.ingest_runs SET finished_at=now(), recipes=%s, status='completed' WHERE run_id=%s",
            (len(RECIPES), run),
        )
        conn.commit()
    print(f"BIOVIZ_SEED_OK recipes={len(RECIPES)} styles={len(STYLES)} dim={model.get_embedding_dimension()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
