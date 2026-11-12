"""PaperQA2 adapted retrieval smoke on SciFact.

Runs only in the isolated PaperQA venv (G:/venvs/paperqa):
  LITELLM_LOCAL_MODEL_COST_MAP=true python eval/paperqa_smoke.py --limit 50

This is retrieval-only: PaperQA Docs + sparse retrieval, no LLM answer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sqlite3
from pathlib import Path

from lmi import SparseEmbeddingModel
from paperqa import Doc, Docs, Text

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "benchmark_scifact.db"
GOLD = ROOT / "eval" / "gold" / "scifact_300.jsonl"


def load_rows():
    conn = sqlite3.connect(str(DB))
    papers = dict(conn.execute("SELECT paper_id, title FROM papers").fetchall())
    sentences = conn.execute(
        "SELECT sentence_id, paper_id, text FROM sentences ORDER BY paper_id, sequence"
    ).fetchall()
    conn.close()
    grouped = {}
    for sentence_id, paper_id, text in sentences:
        grouped.setdefault(paper_id, []).append((sentence_id, text or ""))
    claims = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            claims.append(
                {"claim_id": str(item["id"]), "claim": item["question"], "evidence": item["evidence"]}
            )
    return papers, grouped, claims


async def run(limit: int, k: int) -> dict:
    papers, grouped, claims = load_rows()
    claims = claims[:limit]
    embeddings = SparseEmbeddingModel()
    docs = Docs()
    added = 0
    for paper_id, title in papers.items():
        rows = grouped.get(paper_id, [])
        if not rows:
            continue
        doc = Doc(docname=paper_id, dockey=paper_id, citation=title or paper_id)
        texts = [Text(text=text, name=sentence_id, doc=doc) for sentence_id, text in rows]
        if await docs.aadd_texts(texts, doc, embedding_model=embeddings):
            added += 1
    hit1 = hit5 = hit10 = 0
    recall = 0.0
    rr = 0.0
    rows_out = []
    for claim in claims:
        hits = await docs.retrieve_texts(claim["claim"], k, embedding_model=embeddings)
        gold = set(claim["evidence"])
        found = set()
        first = None
        for rank, hit in enumerate(hits, 1):
            if hit.name in gold and first is None:
                first = rank
            if hit.name in gold:
                found.add(hit.name)
        hit1 += int(first == 1)
        hit5 += int(first is not None and first <= 5)
        hit10 += int(first is not None and first <= 10)
        recall += len(found) / max(len(gold), 1)
        rr += 1.0 / first if first else 0.0
        rows_out.append(
            {
                "claim_id": claim["claim_id"],
                "first_rank": first,
                "top": [hit.name for hit in hits[:3]],
            }
        )
    n = len(claims)
    return {
        "system": "PaperQA2 sparse retrieval (adapted)",
        "claims": n,
        "k": k,
        "docs": added,
        "hit@1": hit1 / n,
        "hit@5": hit5 / n,
        "hit@10": hit10 / n,
        "sentence_recall@10": recall / n,
        "mrr@10": rr / n,
        "rows": rows_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = asyncio.run(run(args.limit, args.k))
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
