"""Rebuild the side collections (papers / figures / tables) for a Chroma index.

``scripts/rebuild_chroma.py`` builds only ``paragraphs``; the retriever also
needs ``papers`` (paper-level title+abstract search) and optionally figures and
tables. Run this after a paragraph rebuild, before switching the index over.

    python scripts/restore_side_collections.py --chroma data/chroma
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

DB = Path(__file__).resolve().parents[1] / "data" / "research.db"
CHROMA = Path(__file__).resolve().parents[1] / "data" / "chroma"
MODEL = Path(r"D:\models\models\BAAI--bge-base-en-v1.5")
BATCH = 64


def rebuild(client, model, name, ids, documents, metadatas):
    try:
        client.delete_collection(name)
    except Exception:  # noqa: BLE001 - collection may not exist
        pass
    collection = client.create_collection(name, metadata={"hnsw:space": "cosine"})
    for index in range(0, len(ids), BATCH):
        chunk = slice(index, index + BATCH)
        texts = documents[chunk]
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()
        collection.add(
            ids=ids[chunk],
            documents=texts,
            metadatas=metadatas[chunk],
            embeddings=embeddings,
        )
    print(f"{name} -> {collection.count()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB))
    parser.add_argument("--chroma", default=str(CHROMA))
    parser.add_argument("--model", default=str(MODEL))
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    model = SentenceTransformer(args.model, device=args.device)
    client = chromadb.PersistentClient(path=args.chroma)
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    papers = [
        {
            "id": row["paper_id"],
            "doc": ((row["title"] or "") + "\n\n" + (row["abstract"] or "")).strip(),
            "meta": {
                "type": "paper",
                "paper_id": row["paper_id"],
                "journal": row["journal"] or "",
                "year": row["year"] or "",
            },
        }
        for row in con.execute("SELECT paper_id, title, abstract, journal, year FROM papers")
        if (row["title"] or "").strip() or (row["abstract"] or "").strip()
    ]
    rebuild(client, model, "papers", [p["id"] for p in papers],
            [p["doc"] for p in papers], [p["meta"] for p in papers])

    figures = [
        {
            "id": row["fig_id"],
            "doc": ((row["fig_number"] or "") + ". " + (row["caption"] or "")).strip(),
            "meta": {
                "fig_number": row["fig_number"] or "",
                "paper_id": row["paper_id"],
                "page": row["page"] or 0,
                "file_path": row["file_path"] or "",
            },
        }
        for row in con.execute("SELECT fig_id, paper_id, fig_number, caption, file_path, page FROM figures")
        if (row["caption"] or "").strip()
    ]
    rebuild(client, model, "figures", [f["id"] for f in figures],
            [f["doc"] for f in figures], [f["meta"] for f in figures])

    tables = [
        {
            "id": row["table_id"],
            "doc": (
                (row["table_number"] or "") + ". " + (row["caption"] or "")
                + "\n" + (row["markdown"] or "")
            ).strip(),
            "meta": {
                "page": row["page"] or 0,
                "table_number": row["table_number"] or "",
                "paper_id": row["paper_id"],
            },
        }
        for row in con.execute("SELECT table_id, paper_id, table_number, caption, markdown, page FROM tables")
        if (row["caption"] or "").strip()
    ]
    rebuild(client, model, "tables", [t["id"] for t in tables],
            [t["doc"] for t in tables], [t["meta"] for t in tables])

    print("collections:", [c.name for c in client.list_collections()])
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
