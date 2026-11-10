"""Per-question attribution for sentence-window retrieval."""

from __future__ import annotations

import argparse
import json
import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.determinism import seed_everything
from services.search.sentence_hybrid import SentenceHybridRetriever, _ts_query  # noqa: E402

GOLD = ROOT / "eval" / "gold" / "seed_100.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=20)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "sentence_window_diag.json"))
    args = parser.parse_args()
    seed_everything(42)

    gold = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines() if line.strip()]
    gold = gold[args.start - 1:args.end]
    retriever = SentenceHybridRetriever(rerank_pool=20, sentence_top_k=100)
    rows = []

    for item in gold:
        expected = set(item.get("evidence") or [])
        started = time.time()
        qvec = retriever.model.encode([item["question"]], normalize_embeddings=True)[0]
        paragraph_hits = retriever.vector.search(qvec, top_k=30)
        para_rank = {hit.para_id: i for i, hit in enumerate(paragraph_hits)}

        pg = retriever._pg()
        try:
            lexical = retriever._lexical_rows(pg, item["question"], 100)
            by_para = retriever._sentences_for_paragraphs(pg, [hit.para_id for hit in paragraph_hits])
            gold_rows = pg.execute(
                "SELECT sentence_id, para_id FROM sentences WHERE sentence_id = ANY(%s)",
                (list(expected),),
            ).fetchall()
        finally:
            pg.close()
        gold_para = {row["sentence_id"]: row["para_id"] for row in gold_rows}
        lex_rank = {row["sentence_id"]: i for i, row in enumerate(lexical, start=1)}

        candidates = {row["sentence_id"]: dict(row) for row in lexical}
        for sentences in by_para.values():
            for row in sentences:
                candidates.setdefault(row["sentence_id"], dict(row))
        scored = []
        for sid, row in candidates.items():
            lex = 0.7 / (60 + lex_rank[sid]) if sid in lex_rank else 0.0
            p_rank = para_rank.get(row["para_id"])
            prior = 0.3 / (60 + p_rank) if p_rank is not None else 0.0
            scored.append((lex + prior, row))
        scored.sort(key=lambda pair: -pair[0])
        pool = scored[:20]
        reranked = retriever.reranker.rerank(
            item["question"],
            [{"sentence_id": row["sentence_id"], "text": (row.get("text") or "")[:800]} for _, row in pool],
            top_k=10,
            batch_size=16,
        )
        final_ids = [hit["sentence_id"] for hit in reranked]
        final_rank = {sid: i for i, sid in enumerate(final_ids, start=1)}

        expected_paras = {gold_para.get(sid) for sid in expected if gold_para.get(sid)}
        recalled_paras = expected_paras & set(para_rank)
        gold_candidate = expected & set(candidates)
        gold_pool = expected & {row["sentence_id"] for _, row in pool}
        gold_final = expected & set(final_ids)

        rows.append(
            {
                "id": item["id"],
                "expected": sorted(expected),
                "expected_paras": sorted(expected_paras),
                "paragraph_rank": min((para_rank[p] for p in recalled_paras), default=None),
                "paragraph_recalled": bool(recalled_paras),
                "lexical_rank": min((lex_rank[s] for s in expected if s in lex_rank), default=None),
                "sentence_candidate": bool(gold_candidate),
                "rerank_pool": bool(gold_pool),
                "rerank_pool_rank": min(
                    (i for i, (_, row) in enumerate(pool, start=1) if row["sentence_id"] in expected),
                    default=None,
                ),
                "final_rank": min((final_rank[s] for s in gold_final), default=None),
                "hit": bool(gold_final),
                "top10": final_ids,
                "sec": round(time.time() - started, 2),
            }
        )
        print(
            f"{item['id']} para={rows[-1]['paragraph_recalled']}@{rows[-1]['paragraph_rank']} "
            f"lex={rows[-1]['lexical_rank']} cand={rows[-1]['sentence_candidate']} "
            f"pool={rows[-1]['rerank_pool']}@{rows[-1]['rerank_pool_rank']} "
            f"final={rows[-1]['final_rank']} hit={rows[-1]['hit']}"
        )

    summary = {
        "n": len(rows),
        "hits": sum(row["hit"] for row in rows),
        "paragraph_recalled": sum(row["paragraph_recalled"] for row in rows),
        "sentence_candidate": sum(row["sentence_candidate"] for row in rows),
        "rerank_pool": sum(row["rerank_pool"] for row in rows),
        "sec_avg": round(sum(row["sec"] for row in rows) / len(rows), 2),
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
