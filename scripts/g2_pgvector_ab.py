"""G2 maintenance A/B: pgvector retrieval, raw paragraphs vs evidence."""

from __future__ import annotations

import json
import math
import os
import statistics
from pathlib import Path

from sentence_transformers import SentenceTransformer

from config.paths import EMBEDDING_MODEL
from services.search.hybrid_search import HybridSearch
from services.search.pg_vector import PGVectorParagraphSearch

CASES = Path("/app/eval/gold/regression_20.jsonl")


def main() -> None:
    cases = [
        json.loads(line)
        for line in CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    model = SentenceTransformer(EMBEDDING_MODEL)
    pg = PGVectorParagraphSearch()

    def vector_search(self, query, top_k=10, paper_id=None, filters=None, collection=None):
        emb = model.encode([query], normalize_embeddings=True)[0]
        hits = pg.search(emb, top_k=top_k, paper_id=paper_id or "")
        return [
            {
                "para_id": hit.para_id,
                "paper_id": hit.paper_id,
                "section_l1": hit.section_level1,
                "section_l2": hit.section_level2,
                "text": hit.text,
                "metadata": {"paper_id": hit.paper_id},
                "score": float(hit.rank),
            }
            for hit in hits
        ]

    HybridSearch.vector_search = vector_search
    from services.search.unified_retriever import UnifiedRetriever

    retriever = UnifiedRetriever(rerank=True, routing=True, expand=True, graph_expand=False)
    rows = []
    for case in cases:
        gold = ""
        for sentence in case.get("evidence") or []:
            if "_sent_" in sentence:
                gold = sentence.rsplit("_sent_", 1)[0]
                break
        question = case["question"]
        env = retriever.retrieve(question, top_paragraphs=10)
        raw = [p.get("para_id") for p in env.get("paragraphs") or []]
        bundle = retriever.to_evidence_json(question, top_paragraphs=10)
        evidence = []
        for item in bundle.get("evidence") or []:
            evidence.extend(p.get("para_id") for p in item.get("paragraph_details") or [])
        rows.append({"id": case["id"], "gold": gold, "raw": raw, "evidence": evidence})

    valid = [r for r in rows if r["gold"]]
    raw_hits = sum(1 for r in valid if r["gold"] in r["raw"])
    evidence_hits = sum(1 for r in valid if r["gold"] in r["evidence"])
    raw_ndcg = statistics.mean(
        1 / math.log2(r["raw"].index(r["gold"]) + 2) if r["gold"] in r["raw"] else 0.0
        for r in valid
    )
    evidence_ndcg = statistics.mean(
        1 / math.log2(r["evidence"].index(r["gold"]) + 2) if r["gold"] in r["evidence"] else 0.0
        for r in valid
    )
    print(
        json.dumps(
            {
                "n": len(valid),
                "raw_recall": round(raw_hits / len(valid), 4),
                "evidence_recall": round(evidence_hits / len(valid), 4),
                "raw_ndcg": round(raw_ndcg, 4),
                "evidence_ndcg": round(evidence_ndcg, 4),
            }
        )
    )
    for row in rows:
        if row["gold"] and row["gold"] in row["raw"] and row["gold"] not in row["evidence"]:
            print("LOST", row["id"], row["gold"], flush=True)


if __name__ == "__main__":
    main()
