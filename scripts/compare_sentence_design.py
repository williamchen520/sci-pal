"""Compare legacy HTTP retrieval with sentence-hybrid prototype.

This is an evaluation harness, not production routing.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.pg_pool import pg_connection
from config.paths import EMBEDDING_MODEL
from services.search.pg_vector import PGVectorParagraphSearch
from services.search.reranker import Reranker
from sentence_transformers import SentenceTransformer


def load_gold(path: Path, limit: int):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def sentence_hits(pg, query: str, limit: int = 100):
    rows = pg.execute(
        "SELECT sentence_id, para_id, paper_id, text, "
        "ts_rank(search_vector, plainto_tsquery('english', %s)) AS rank "
        "FROM sentences WHERE search_vector @@ plainto_tsquery('english', %s) "
        "ORDER BY rank DESC LIMIT %s",
        (query, query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def sentences_for_paragraphs(pg, para_ids, limit: int = 400):
    if not para_ids:
        return []
    rows = pg.execute(
        "SELECT sentence_id, para_id, paper_id, text, sequence "
        "FROM sentences WHERE para_id = ANY(%s) ORDER BY para_id, sequence LIMIT %s",
        (list(para_ids), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def new_engine(query: str, model, vector, reranker, *, para_k: int, sent_k: int):
    _t0 = time.time()
    qv = model.encode([query], normalize_embeddings=True)[0]
    pg_hits = vector.search(qv, top_k=para_k)
    para_scores = {hit.para_id: float(hit.rank) for hit in pg_hits}
    max_para = max(para_scores.values(), default=1.0) or 1.0

    pg = pg_connection()
    try:
        lexical = sentence_hits(pg, query, limit=sent_k)
        from_vec = sentences_for_paragraphs(pg, list(para_scores)[:para_k])
    finally:
        pg.close()

    merged = {}
    for row in lexical:
        merged[row["sentence_id"]] = {
            **row,
            "lexical": float(row.get("rank") or 0.0),
            "prior": para_scores.get(row["para_id"], 0.0) / max_para,
        }
    for row in from_vec:
        item = merged.setdefault(
            row["sentence_id"],
            {**row, "lexical": 0.0, "prior": para_scores.get(row["para_id"], 0.0) / max_para},
        )
        item["prior"] = para_scores.get(row["para_id"], 0.0) / max_para

    if not merged:
        return [], 0.0
    max_lex = max((item["lexical"] for item in merged.values()), default=1.0) or 1.0
    candidates = []
    for item in merged.values():
        score = 0.65 * (item["lexical"] / max_lex) + 0.35 * item["prior"]
        candidates.append({**item, "score": score})
    candidates.sort(key=lambda item: -item["score"])
    pool = candidates[:100]
    started = time.time()
    reranked = reranker.rerank(
        query,
        [{"sentence_id": row["sentence_id"], "text": (row.get("text") or "")[:800]} for row in pool],
        top_k=10,
        batch_size=16,
    )
    elapsed = time.time() - started
    total = time.time() - _t0
    by_id = {row["sentence_id"]: row for row in pool}
    out = []
    for row in reranked:
        base = by_id[row["sentence_id"]]
        out.append({
            "sentence_id": base["sentence_id"],
            "paper_id": base["paper_id"],
            "para_id": base["para_id"],
            "text": base.get("text", ""),
            "rerank_score": row.get("rerank_score"),
        })
    return out, total, {item["sentence_id"] for item in candidates}


def legacy_http(question: str, base_url: str, top_k: int = 10):
    body = json.dumps({"query": question, "top_k": top_k}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/evidence/search",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    started = time.time()
    with urllib.request.urlopen(req, timeout=600) as response:
        payload = json.loads(response.read())
    elapsed = time.time() - started
    ids = []
    for item in payload.get("evidence") or []:
        for hit in item.get("highlight") or []:
            if hit.get("sentence_id"):
                ids.append(hit["sentence_id"])
    return ids, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--para-k", type=int, default=30)
    parser.add_argument("--sent-k", type=int, default=100)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "sentence_hybrid_compare.json"))
    parser.add_argument("--skip-legacy", action="store_true")
    args = parser.parse_args()

    gold = load_gold(ROOT / "eval" / "gold" / "seed_100.jsonl", args.limit)
    model = SentenceTransformer(os.environ.get("SCIPAL_EMBEDDING_MODEL", EMBEDDING_MODEL))
    vector = PGVectorParagraphSearch()
    reranker = Reranker()

    rows = []
    for item in gold:
        expected = set(item.get("evidence") or [])
        if args.skip_legacy:
            old_ids, old_sec = [], 0.0
        else:
            old_ids, old_sec = legacy_http(item["question"], args.base_url, args.top_k)
        new_ids, new_rerank_sec, candidate_ids = new_engine(
            item["question"], model, vector, reranker, para_k=args.para_k, sent_k=args.sent_k
        )
        new_id_list = [row["sentence_id"] for row in new_ids]
        rows.append({
            "id": item["id"],
            "question": item["question"],
            "legacy_sec": round(old_sec, 2),
            "new_sec": round(new_rerank_sec, 2),
            "legacy_hit": bool(expected & set(old_ids)),
            "new_hit": bool(expected & set(new_id_list)),
            "candidate_hit": bool(expected & candidate_ids),
            "expected": sorted(expected),
            "legacy_top10": old_ids[:10],
            "new_top10": new_id_list[:10],
        })
        print(f"{item['id']} legacy={old_sec:.1f}s new_rerank={new_rerank_sec:.1f}s "
              f"hit_new={rows[-1]['new_hit']}")

    summary = {
        "n": len(rows),
        "legacy_recall": round(sum(r["legacy_hit"] for r in rows) / len(rows), 4),
        "new_recall": round(sum(r["new_hit"] for r in rows) / len(rows), 4),
        "legacy_sec_avg": round(sum(r["legacy_sec"] for r in rows) / len(rows), 2),
        "new_rerank_sec_avg": round(sum(r["new_sec"] for r in rows) / len(rows), 2),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("saved", out)


if __name__ == "__main__":
    main()
