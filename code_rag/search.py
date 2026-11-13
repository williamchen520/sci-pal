"""Library-scoped hybrid code search over scipal_code (P3)."""

from __future__ import annotations

import argparse
import json
import os
import re

import psycopg
from sentence_transformers import SentenceTransformer

from code_rag.ranking import path_weight

MODEL = os.environ.get("SCIPAL_CODE_EMBED_MODEL", r"G:/models/bge-small-zh-v1.5")


def _dsn() -> str:
    value = os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not value:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    return value



def search(
    query: str,
    *,
    library_id: str,
    top_k: int = 10,
    snapshot_id: str = "",
    dsn: str | None = None,
    model: SentenceTransformer | None = None,
) -> list[dict]:
    dsn = dsn or _dsn()
    model = model or SentenceTransformer(MODEL, device=os.environ.get("SCIPAL_CODE_DEVICE", "cuda"))
    vector = json.dumps(model.encode([query], normalize_embeddings=True)[0].tolist())
    with psycopg.connect(dsn) as conn:
        vec = conn.execute(
            """
            SELECT e.unit_id
            FROM code_rag.code_embeddings e
            JOIN code_rag.code_units u ON u.unit_id=e.unit_id
            WHERE u.library_id=%s AND (%s='' OR u.snapshot_id=%s)
              AND u.unit_type <> 'file'
            ORDER BY e.embedding <=> %s::vector
            LIMIT 40
            """,
            (library_id, snapshot_id, snapshot_id, vector),
        ).fetchall()
        lex = conn.execute(
            """
            SELECT unit_id
            FROM code_rag.code_units
            WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
              AND unit_type <> 'file'
              AND GREATEST(
                similarity(symbol_name, %s),
                similarity(text, %s),
                word_similarity(%s, symbol_name)
              ) > 0.02
            ORDER BY GREATEST(
              similarity(symbol_name, %s),
              similarity(text, %s),
              word_similarity(%s, symbol_name)
            ) DESC
            LIMIT 40
            """,
            (library_id, snapshot_id, snapshot_id, query, query, query, query, query, query),
        ).fetchall()
        exact = conn.execute(
            """
            SELECT unit_id FROM code_rag.code_units
            WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
              AND (lower(symbol_name)=lower(%s) OR lower(symbol_name)=lower(%s))
            LIMIT 5
            """,
            (
                library_id,
                snapshot_id,
                snapshot_id,
                query,
                query.strip().lower().replace(" ", "_"),
            ),
        ).fetchall()

        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) >= 3 and token not in {"the", "and", "for", "with", "from", "per"}
        ]
        symbol_rows = []
        if tokens:
            symbol_rows = conn.execute(
                """
                SELECT unit_id, symbol_name FROM code_rag.code_units
                WHERE library_id=%s AND (%s='' OR snapshot_id=%s)
                  AND lower(symbol_name) LIKE ANY(%s)
                LIMIT 2000
                """,
                (library_id, snapshot_id, snapshot_id, [f"%{token}%" for token in tokens]),
            ).fetchall()

        scores: dict[str, float] = {}
        for rank, (unit_id,) in enumerate(vec, 1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (60 + rank)
        for rank, (unit_id,) in enumerate(lex, 1):
            scores[unit_id] = scores.get(unit_id, 0.0) + 1.0 / (60 + rank)
        for unit_id, in exact:
            scores[unit_id] = scores.get(unit_id, 0.0) + 3.0 / 61
        query_norm = query.strip().lower().replace(" ", "_")
        generic = {"read", "write", "get", "set", "run", "main", "test", "load", "save", "plot"}
        for unit_id, symbol in symbol_rows:
            name = (symbol or "").lower()
            if not name:
                continue
            exact_name = name in tokens
            matched = sum(1 for token in tokens if token in name or token[:5] in name)
            if exact_name and name in generic:
                boost = 0.3
            elif exact_name:
                boost = 2.0
            elif query_norm.startswith(name) or name.startswith(query_norm):
                boost = 1.5
            else:
                boost = 1.2 * matched / max(len(tokens), 1)
            scores[unit_id] = scores.get(unit_id, 0.0) + boost
        if not scores:
            return []
        ids = list(scores)
        rows = conn.execute(
            """
            SELECT u.unit_id, u.library_id, u.snapshot_id, u.symbol_name, u.unit_type,
                   u.text, u.start_line, u.end_line, f.path
            FROM code_rag.code_units u
            JOIN code_rag.code_files f ON f.file_id=u.file_id
            WHERE u.unit_id = ANY(%s)
            """,
            (ids,),
        ).fetchall()
        by_id = {row[0]: row for row in rows}
        for unit_id, row in by_id.items():
            scores[unit_id] *= path_weight(query, row[8] or "")
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    result = []
    for unit_id, score in ordered:
        row = by_id.get(unit_id)
        if not row:
            continue
        result.append(
            {
                "unit_id": row[0],
                "library_id": row[1],
                "snapshot_id": row[2],
                "symbol_name": row[3],
                "unit_type": row[4],
                "snippet": (row[5] or "")[:500],
                "start_line": row[6],
                "end_line": row[7],
                "path": row[8],
                "score": score,
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    hits = search(
        args.query,
        library_id=args.library_id,
        top_k=args.top_k,
        snapshot_id=args.snapshot_id,
    )
    if args.json:
        print(json.dumps({"query": args.query, "library_id": args.library_id, "hits": hits}, ensure_ascii=False, indent=2))
    else:
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit['symbol_name']} [{hit['unit_type']}] {hit['path']}:{hit['start_line']} score={hit['score']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
