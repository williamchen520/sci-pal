#!/usr/bin/env python3
"""SciFact retrieval comparison: pgvector HNSW vs exact vs Chroma."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from pathlib import Path

import chromadb
import psycopg
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "eval" / "data" / "scifact" / "scifact"
DEFAULT_MODEL = Path("G:/sciPal_deploy/models/models/BAAI--bge-base-en-v1.5")


def load(base: Path):
    corpus = [json.loads(line) for line in (base / "corpus.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    queries = {row["_id"]: row["text"] for row in (json.loads(line) for line in (base / "queries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    qrels = {}
    for line in (base / "qrels" / "test.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        qid, doc_id, score = line.split("\t")
        if int(score) > 0:
            qrels.setdefault(qid, set()).add(doc_id)
    return corpus, queries, qrels


def ndcg(ids, gold, k=10):
    dcg = sum(1.0 / math.log2(rank + 2) for rank, doc in enumerate(ids[:k]) if doc in gold)
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(min(k, len(gold))))
    return dcg / ideal if ideal else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--out", default="eval/results/scifact_backends.json")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    corpus, queries, qrels = load(Path(args.data))
    qids = sorted(qrels)
    if args.limit:
        qids = qids[: args.limit]
    model = SentenceTransformer(args.model, device="cuda" if _cuda() else "cpu")
    docs = [f"{row.get('title', '')}. {row.get('text', '')}" for row in corpus]
    doc_ids = [str(row["_id"]) for row in corpus]
    doc_vecs = model.encode(docs, batch_size=64, normalize_embeddings=True, show_progress_bar=False)

    chroma_path = Path("eval/data/scifact_chroma")
    if chroma_path.exists():
        shutil.rmtree(chroma_path, ignore_errors=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    coll = client.get_or_create_collection("scifact", metadata={"hnsw:space": "cosine"})
    coll.add(ids=doc_ids, embeddings=doc_vecs.tolist(), documents=docs)
    print(f"docs={len(doc_ids)} queries={len(qids)}", flush=True)

    pg = psycopg.connect(args.dsn)
    pg.autocommit = True
    pg.execute("CREATE EXTENSION IF NOT EXISTS vector")
    pg.execute("DROP TABLE IF EXISTS scifact_eval_docs")
    pg.execute("CREATE TABLE scifact_eval_docs (doc_id text PRIMARY KEY, embedding vector(768) NOT NULL)")
    with pg.cursor() as cur:
        cur.executemany(
            "INSERT INTO scifact_eval_docs (doc_id, embedding) VALUES (%s, %s::vector)",
            [(doc_id, "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]") for doc_id, vec in zip(doc_ids, doc_vecs)],
        )
    pg.execute("CREATE INDEX scifact_eval_hnsw ON scifact_eval_docs USING hnsw (embedding vector_cosine_ops)")
    print("indexes ready", flush=True)

    rows = []
    for qid in qids:
        qvec = model.encode([queries[qid]], normalize_embeddings=True)[0]
        lit = "[" + ",".join(f"{float(v):.6f}" for v in qvec) + "]"
        pg_hits = [r[0] for r in pg.execute(
            "SELECT doc_id FROM scifact_eval_docs ORDER BY embedding <=> %s::vector LIMIT 10", (lit,)
        ).fetchall()]
        ch_hits = coll.query(query_embeddings=[qvec.tolist()], n_results=10)["ids"][0]
        pg.execute("SET enable_indexscan=off")
        pg.execute("SET enable_bitmapscan=off")
        exact_hits = [r[0] for r in pg.execute(
            "SELECT doc_id FROM scifact_eval_docs ORDER BY embedding <=> %s::vector LIMIT 10", (lit,)
        ).fetchall()]
        pg.execute("SET enable_indexscan=on")
        pg.execute("SET enable_bitmapscan=on")
        gold = qrels[qid]
        rows.append({
            "qid": qid,
            "pg_recall": len(set(pg_hits) & gold) / len(gold),
            "pg_ndcg": ndcg(pg_hits, gold),
            "chroma_recall": len(set(ch_hits) & gold) / len(gold),
            "chroma_ndcg": ndcg(ch_hits, gold),
            "exact_recall": len(set(exact_hits) & gold) / len(gold),
            "exact_ndcg": ndcg(exact_hits, gold),
            "pg_exact_overlap": len(set(pg_hits) & set(exact_hits)),
            "pg_chroma_overlap": len(set(pg_hits) & set(ch_hits)),
        })
    pg.execute("DROP TABLE IF EXISTS scifact_eval_docs")
    pg.close()
    summary = {
        key: round(sum(row[key] for row in rows) / len(rows), 4)
        for key in ("pg_recall", "pg_ndcg", "chroma_recall", "chroma_ndcg", "exact_recall", "exact_ndcg", "pg_exact_overlap", "pg_chroma_overlap")
    }
    summary["queries"] = len(rows)
    out = {"summary": summary, "rows": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary, flush=True)
    return 0


def _cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    raise SystemExit(main())
