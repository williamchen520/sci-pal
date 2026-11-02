#!/usr/bin/env python3
"""Prune orphan paragraph vectors and backfill missing ones.

This is a maintenance script, not a full rebuild. It:
1. reads current para_ids from SQLite;
2. deletes Chroma ids that no longer exist in SQLite;
3. embeds and upserts SQLite paragraphs missing from Chroma.

Run with --dry-run first. Stop the API before applying in production.
"""

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


def load_paragraphs(db: Path) -> dict[str, dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT para_id, paper_id, section_level1, section_level2, text, sequence "
            "FROM paragraphs WHERE text IS NOT NULL AND length(trim(text)) >= 10"
        ).fetchall()
    finally:
        conn.close()
    return {row["para_id"]: dict(row) for row in rows}


def delete_ids(collection, ids: list[str], batch_size: int) -> int:
    deleted = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        collection.delete(ids=batch)
        deleted += len(batch)
    return deleted


def run(args) -> dict:
    import chromadb

    paragraphs = load_paragraphs(Path(args.sqlite))
    db_ids = set(paragraphs)
    client = chromadb.PersistentClient(path=str(args.chroma))
    collection = client.get_or_create_collection(
        name=args.collection, metadata={"hnsw:space": "cosine"}
    )
    before = collection.count()
    existing = set(collection.get(include=[])["ids"])
    orphan = sorted(existing - db_ids)
    missing = sorted(db_ids - existing)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sqlite": str(args.sqlite),
        "chroma": str(args.chroma),
        "collection": args.collection,
        "db_paragraphs": len(db_ids),
        "vectors_before": before,
        "orphans": len(orphan),
        "missing": len(missing),
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        report["orphan_sample"] = orphan[:10]
        report["missing_sample"] = missing[:10]
        return report

    if orphan:
        report["deleted"] = delete_ids(collection, orphan, args.batch_size)
    else:
        report["deleted"] = 0

    if missing:
        import torch
        from sentence_transformers import SentenceTransformer

        model_path = args.model or os.environ.get("SCIPAL_EMBEDDING_MODEL") or DEFAULT_MODEL
        device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"embedding device: {device}", flush=True)
        model = SentenceTransformer(model_path, device=device)
        inserted = 0
        for start in range(0, len(missing), args.batch_size):
            batch_ids = missing[start : start + args.batch_size]
            rows = [paragraphs[i] for i in batch_ids]
            texts = [row["text"] for row in rows]
            embeddings = model.encode(
                texts, batch_size=args.batch_size, show_progress_bar=False
            )
            collection.upsert(
                ids=batch_ids,
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=[
                    {
                        "paper_id": row["paper_id"],
                        "section_l1": row["section_level1"] or "",
                        "section_l2": row["section_level2"] or "",
                        "sequence": row["sequence"] or 0,
                    }
                    for row in rows
                ],
            )
            inserted += len(batch_ids)
            if (start // args.batch_size) % 10 == 0:
                print(f"backfilled {inserted}/{len(missing)}", flush=True)
        report["inserted"] = inserted
    else:
        report["inserted"] = 0

    after_ids = set(collection.get(include=[])["ids"])
    report["vectors_after"] = len(after_ids)
    report["resolved_after"] = len(after_ids & db_ids)
    report["orphans_after"] = len(after_ids - db_ids)
    report["missing_after"] = len(db_ids - after_ids)
    report["coverage_after"] = round(len(after_ids & db_ids) / len(db_ids), 4) if db_ids else None
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--collection", default="paragraphs")
    parser.add_argument("--model", default="")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--device", default="")
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
