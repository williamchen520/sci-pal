"""Search over the independent scipal_docs database.

Modes:
  vector   pgvector HNSW only
  lexical  pg_trgm similarity / word_similarity only
  hybrid   RRF fusion of both
"""

from __future__ import annotations

import argparse
import json
import os

import psycopg
from sentence_transformers import SentenceTransformer

MODEL = os.environ.get("SCIPAL_DOCS_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")
QUERY_PREFIX = os.environ.get("SCIPAL_DOCS_QUERY_PREFIX", "")
MODES = {"vector", "lexical", "hybrid"}

_VECTOR_SQL = """
SELECT c.chunk_id, c.doc_id, c.heading, c.text,
       d.path, d.title, d.category,
       1 - (e.embedding <=> %s::vector) AS score
FROM docs_rag.embeddings e
JOIN docs_rag.chunks c ON c.chunk_id = e.chunk_id
JOIN docs_rag.documents d ON d.doc_id = c.doc_id
ORDER BY e.embedding <=> %s::vector
LIMIT %s
"""

_LEXICAL_SQL = """
WITH q AS (SELECT %s::text AS text)
SELECT c.chunk_id, c.doc_id, c.heading, c.text,
       d.path, d.title, d.category,
       GREATEST(
         similarity(c.text, q.text),
         word_similarity(q.text, c.text),
         similarity(d.title, q.text),
         word_similarity(q.text, d.title)
       ) AS score
FROM docs_rag.chunks c
JOIN docs_rag.documents d ON d.doc_id = c.doc_id
CROSS JOIN q
WHERE GREATEST(
  similarity(c.text, q.text),
  word_similarity(q.text, c.text),
  similarity(d.title, q.text),
  word_similarity(q.text, d.title)
) > 0.02
ORDER BY score DESC
LIMIT %s
"""

_HYBRID_SQL = """
WITH q AS (SELECT %s::text AS text),
vec AS (
  SELECT c.chunk_id,
         row_number() OVER (ORDER BY e.embedding <=> %s::vector) AS rnk
  FROM docs_rag.embeddings e
  JOIN docs_rag.chunks c ON c.chunk_id = e.chunk_id
  ORDER BY e.embedding <=> %s::vector
  LIMIT %s
),
lex AS (
  SELECT c.chunk_id,
         row_number() OVER (
           ORDER BY GREATEST(
             similarity(c.text, q.text),
             word_similarity(q.text, c.text),
             similarity(d.title, q.text),
             word_similarity(q.text, d.title)
           ) DESC
         ) AS rnk
  FROM docs_rag.chunks c
  JOIN docs_rag.documents d ON d.doc_id = c.doc_id
  CROSS JOIN q
  WHERE GREATEST(
    similarity(c.text, q.text),
    word_similarity(q.text, c.text),
    similarity(d.title, q.text),
    word_similarity(q.text, d.title)
  ) > 0.02
  ORDER BY GREATEST(
    similarity(c.text, q.text),
    word_similarity(q.text, c.text),
    similarity(d.title, q.text),
    word_similarity(q.text, d.title)
  ) DESC
  LIMIT %s
),
fused AS (
  SELECT chunk_id, 1.0 / (60 + rnk) AS score FROM vec
  UNION ALL
  SELECT chunk_id, 1.0 / (60 + rnk) AS score FROM lex
)
SELECT c.chunk_id, c.doc_id, c.heading, c.text,
       d.path, d.title, d.category, SUM(f.score) AS score
FROM fused f
JOIN docs_rag.chunks c ON c.chunk_id = f.chunk_id
JOIN docs_rag.documents d ON d.doc_id = c.doc_id
GROUP BY c.chunk_id, c.doc_id, c.heading, c.text, d.path, d.title, d.category
ORDER BY score DESC
LIMIT %s
"""


def _dsn() -> str:
    value = os.environ.get("SCIPAL_DOCS_READ_DSN") or os.environ.get("SCIPAL_DOCS_DSN", "")
    if not value:
        raise SystemExit("SCIPAL_DOCS_READ_DSN or SCIPAL_DOCS_DSN is required")
    return value


def search(
    query: str,
    *,
    top_k: int = 8,
    dsn: str | None = None,
    model: SentenceTransformer | None = None,
    mode: str = "hybrid",
) -> list[dict]:
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    dsn = dsn or _dsn()
    vector = None
    if mode != "lexical":
        model = model or SentenceTransformer(MODEL, device=os.environ.get("SCIPAL_DOCS_DEVICE", "cuda"))
        vector = json.dumps(
            model.encode([QUERY_PREFIX + query], normalize_embeddings=True)[0].tolist()
        )

    with psycopg.connect(dsn) as conn:
        if mode in {"vector", "hybrid"}:
            conn.execute("SET LOCAL hnsw.ef_search = 80")
        if mode == "vector":
            rows = conn.execute(_VECTOR_SQL, (vector, vector, top_k)).fetchall()
        elif mode == "lexical":
            rows = conn.execute(_LEXICAL_SQL, (query, top_k)).fetchall()
        else:
            rows = conn.execute(
                _HYBRID_SQL,
                (query, vector, vector, max(top_k * 8, 40), max(top_k * 8, 40), top_k),
            ).fetchall()

    return [
        {
            "chunk_id": row[0],
            "doc_id": row[1],
            "heading": row[2],
            "text": row[3],
            "path": row[4],
            "title": row[5],
            "category": row[6],
            "score": float(row[7]),
        }
        for row in rows
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--mode", choices=sorted(MODES), default="hybrid")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    hits = search(args.query, top_k=args.top_k, mode=args.mode)
    if args.json:
        print(
            json.dumps(
                {"query": args.query, "mode": args.mode, "hits": hits},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"QUERY {args.query} [{args.mode}]")
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit['title']} [{hit['category']}] {hit['path']}")
            print(f"   {hit['heading']}")
            print(f"   {hit['text'][:180].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
