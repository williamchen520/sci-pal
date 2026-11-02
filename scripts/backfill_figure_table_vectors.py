#!/usr/bin/env python3
"""Backfill missing figure and table vectors from captions."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("G:/sciPal_deploy/data/research.db")
DEFAULT_CHROMA = Path("G:/sciPal_deploy/data/chroma")
DEFAULT_MODEL = "D:/models/models/BAAI--bge-base-en-v1.5"


def run(args) -> dict:
    import chromadb
    import torch
    from sentence_transformers import SentenceTransformer

    conn = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    client = chromadb.PersistentClient(path=str(args.chroma))
    existing_names = {c.name for c in client.list_collections()}
    fig_col = client.get_collection("figures") if "figures" in existing_names else None
    tbl_col = client.get_collection("tables") if "tables" in existing_names else None

    figures: list[dict] = []
    if fig_col:
        existing = set(fig_col.get(include=[])["ids"])
        for row in conn.execute(
            "SELECT fig_id,paper_id,fig_number,caption,file_path,page FROM figures "
            "WHERE caption IS NOT NULL AND length(trim(caption)) > 5"
        ):
            if row["fig_id"] not in existing:
                figures.append(dict(row))

    tables: list[dict] = []
    if tbl_col:
        existing = set(tbl_col.get(include=[])["ids"])
        for row in conn.execute(
            'SELECT table_id,paper_id,table_number,caption,markdown,page FROM "tables" '
            "WHERE (caption IS NOT NULL AND length(trim(caption)) > 5) "
            "OR (markdown IS NOT NULL AND length(trim(markdown)) > 20)"
        ):
            if row["table_id"] not in existing:
                tables.append(dict(row))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "figures_missing": len(figures),
        "tables_missing": len(tables),
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        report["figure_sample"] = [r["fig_id"] for r in figures[:5]]
        report["table_sample"] = [r["table_id"] for r in tables[:5]]
        conn.close()
        return report

    model_path = args.model or os.environ.get("SCIPAL_EMBEDDING_MODEL") or DEFAULT_MODEL
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = SentenceTransformer(model_path, device=device)

    def embed_upsert(collection, rows, text_fn, meta_fn):
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            texts = [text_fn(row) for row in batch]
            embeddings = model.encode(
                texts, batch_size=args.batch_size, show_progress_bar=False
            )
            collection.upsert(
                ids=[row["id"] for row in batch],
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=[meta_fn(row) for row in batch],
            )
            print(f"upserted {min(start + len(batch), len(rows))}/{len(rows)}", flush=True)

    if fig_col and figures:
        for row in figures:
            row["id"] = row["fig_id"]
        embed_upsert(
            fig_col,
            figures,
            lambda r: f"{r['fig_number'] or 'Figure'}. {r['caption'] or ''}",
            lambda r: {
                "paper_id": r["paper_id"],
                "fig_number": r["fig_number"] or "",
                "file_path": r["file_path"] or "",
                "page": r["page"] or 0,
            },
        )
    if tbl_col and tables:
        for row in tables:
            row["id"] = row["table_id"]
            row["text"] = (
                f"{row['table_number'] or 'Table'}. {row['caption'] or ''}\n"
                f"{(row['markdown'] or '')[:1500]}"
            )
        embed_upsert(
            tbl_col,
            tables,
            lambda r: r["text"],
            lambda r: {
                "paper_id": r["paper_id"],
                "table_number": r["table_number"] or "",
                "page": r["page"] or 0,
            },
        )

    report["figures_upserted"] = len(figures)
    report["tables_upserted"] = len(tables)
    report["vectors_after"] = {
        "figures": fig_col.count() if fig_col else None,
        "tables": tbl_col.count() if tbl_col else None,
    }
    conn.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--model", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = run(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
