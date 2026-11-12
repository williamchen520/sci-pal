"""PaperQA2 adapted abstract-level dense smoke.

Runs in the isolated PaperQA venv:
  LITELLM_LOCAL_MODEL_COST_MAP=true python eval/paperqa_abstract_smoke.py

This is paper-level retrieval, not sentence-level evidence retrieval.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from lmi import SentenceTransformerEmbeddingModel
from paperqa import Doc, Docs, Text

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "benchmark_scifact.db"
GOLD = ROOT / "eval" / "gold" / "scifact_300.jsonl"


def load():
    conn = sqlite3.connect(str(DB))
    papers = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT paper_id, title, abstract FROM papers").fetchall()
    }
    sentences = conn.execute("SELECT sentence_id, paper_id FROM sentences").fetchall()
    conn.close()
    paper_of = {sentence_id: paper_id for sentence_id, paper_id in sentences}
    claims = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            claims.append(
                {"claim_id": str(item["id"]), "claim": item["question"], "evidence": item["evidence"]}
            )
    return papers, paper_of, claims


async def run(limit: int, k: int, model: str, device: str, max_docs: int) -> dict:
    papers, paper_of, claims = load()
    claims = claims[:limit]
    gold_papers = {
        paper_of[item]
        for claim in claims
        for item in claim["evidence"]
        if item in paper_of
    }
    selected = set(gold_papers)
    for paper_id in papers:
        if max_docs and len(selected) >= max_docs:
            break
        selected.add(paper_id)
    embeddings = SentenceTransformerEmbeddingModel(name=model, config={"device": device})
    docs = Docs()
    for paper_id in selected:
        title, abstract = papers[paper_id]
        doc = Doc(docname=paper_id, dockey=paper_id, citation=title or paper_id)
        text = Text(text=abstract or title or "", name=paper_id, doc=doc)
        await docs.aadd_texts([text], doc, embedding_model=embeddings)

    hit1 = hit5 = hit10 = 0
    recall = 0.0
    rr = 0.0
    rows = []
    for claim in claims:
        hits = await docs.retrieve_texts(claim["claim"], k, embedding_model=embeddings)
        gold = {paper_of[item] for item in claim["evidence"] if item in paper_of}
        first = None
        found = set()
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
        rows.append({"claim_id": claim["claim_id"], "first_rank": first})
    n = len(claims)
    return {
        "system": "PaperQA2 dense abstract retrieval (adapted)",
        "claims": n,
        "docs": len(selected),
        "max_docs": max_docs,
        "k": k,
        "model": model,
        "device": device,
        "hit@1": hit1 / n,
        "hit@5": hit5 / n,
        "hit@10": hit10 / n,
        "evidence_paper_recall@10": recall / n,
        "mrr@10": rr / n,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--model", default=r"G:/models/bge-small-en-v1.5")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-docs", type=int, default=1000)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = asyncio.run(
        run(args.limit, args.k, args.model, args.device, args.max_docs)
    )
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
