"""Ingest docs/ into the independent scipal_docs database.

Never imports the Flask app and never uses core/corpus connections.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from docs_rag.chunking import chunk_markdown  # noqa: E402
from scripts.build_docs_index import CATEGORIES, category, title_and_summary  # noqa: E402

GENERATED = {
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "_index" / "all.md",
    *{ROOT / "docs" / name / "README.md" for name in CATEGORIES},
}


def doc_files(docs_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in docs_dir.rglob("*.md")
        if path.resolve() not in {p.resolve() for p in GENERATED}
    )


def doc_id_for(path: Path, docs_dir: Path) -> str:
    rel = path.relative_to(docs_dir).as_posix()
    return "doc_" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_DOCS_DSN", ""))
    parser.add_argument("--docs", default=str(ROOT / "docs"))
    parser.add_argument("--model", default=os.environ.get("SCIPAL_DOCS_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5"))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.dsn:
        raise SystemExit("SCIPAL_DOCS_DSN is required")

    docs_dir = Path(args.docs)
    files = doc_files(docs_dir)
    if args.limit:
        files = files[: args.limit]
    device = os.environ.get("SCIPAL_DOCS_DEVICE", "cuda")
    model = SentenceTransformer(args.model, device=device)
    dim = model.get_sentence_embedding_dimension()
    if dim != 512:
        raise SystemExit(f"docs_rag schema expects 512 dimensions, model returns {dim}")

    total_docs = 0
    total_chunks = 0
    with psycopg.connect(args.dsn) as conn:
        run = conn.execute(
            "INSERT INTO docs_rag.ingest_runs (model, status) VALUES (%s, 'running') RETURNING run_id",
            (args.model,),
        ).fetchone()[0]
        for path in files:
            rel = path.relative_to(docs_dir).as_posix()
            content = path.read_text(encoding="utf-8", errors="ignore")
            title, summary = title_and_summary(path)
            doc_id = doc_id_for(path, docs_dir)
            chunks = chunk_markdown(content)
            conn.execute(
                """
                INSERT INTO docs_rag.documents
                  (doc_id, path, title, category, summary, content, content_sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (path) DO UPDATE SET
                  title=EXCLUDED.title, category=EXCLUDED.category,
                  summary=EXCLUDED.summary, content=EXCLUDED.content,
                  content_sha256=EXCLUDED.content_sha256, updated_at=now()
                """,
                (
                    doc_id,
                    rel,
                    title,
                    category(path),
                    summary,
                    content,
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                ),
            )
            conn.execute("DELETE FROM docs_rag.chunks WHERE doc_id=%s", (doc_id,))
            if chunks:
                embeddings = model.encode(
                    [f"{title}\n{chunk.heading}\n{chunk.text}" for chunk in chunks],
                    batch_size=32,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                rows = []
                for chunk, vector in zip(chunks, embeddings):
                    chunk_id = f"{doc_id}_c{chunk.ordinal:04d}"
                    conn.execute(
                        """
                        INSERT INTO docs_rag.chunks
                          (chunk_id, doc_id, ordinal, heading, text, token_count, metadata)
                        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                        """,
                        (
                            chunk_id,
                            doc_id,
                            chunk.ordinal,
                            chunk.heading,
                            chunk.text,
                            chunk.token_count,
                            json.dumps({"path": rel, "title": title}, ensure_ascii=False),
                        ),
                    )
                    rows.append((chunk_id, json.dumps(vector.tolist()), args.model))
                for row in rows:
                    conn.execute(
                        "INSERT INTO docs_rag.embeddings (chunk_id, embedding, model) VALUES (%s,%s::vector,%s)",
                        row,
                    )
            conn.commit()
            total_docs += 1
            total_chunks += len(chunks)
            if total_docs % 25 == 0:
                print(f"progress docs={total_docs} chunks={total_chunks}", flush=True)

        conn.execute(
            "UPDATE docs_rag.ingest_runs SET finished_at=now(), docs=%s, chunks=%s, status='completed' WHERE run_id=%s",
            (total_docs, total_chunks, run),
        )
        conn.commit()

    print(f"DOCS_RAG_INGEST_OK docs={total_docs} chunks={total_chunks} dim={dim}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
