"""SciFact RRF weight sweep on the existing benchmark index."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "benchmark_scifact.db"
DEFAULT_CHROMA = ROOT / "data" / "benchmark_scifact_chroma"
DEFAULT_OUT = ROOT / "eval" / "results" / "scifact_weight_sweep.json"
RRF_K = 60


def fuse(vector, fts, vw, fw, top_k=10):
    scores = {}
    lookup = {}
    for weight, ranking in ((vw, vector), (fw, fts)):
        for rank, item in enumerate(ranking, 1):
            pid = item.get("para_id")
            if not pid:
                continue
            item.setdefault("paper_id", (item.get("metadata") or {}).get("paper_id"))
            scores[pid] = scores.get(pid, 0.0) + weight / (RRF_K + rank)
            lookup.setdefault(pid, item)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [{**lookup[pid], "score": score} for pid, score in ordered]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--chroma", default=str(DEFAULT_CHROMA))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    import services.search.hybrid_search as hs

    hs.DB_PATH = Path(args.db)
    hs.CHROMA_PATH = Path(args.chroma)
    searcher = hs.HybridSearch()
    conn = sqlite3.connect(args.db)
    claims = conn.execute(
        "SELECT claim_id, claim, cited_doc_ids, evidence FROM claims ORDER BY claim_id LIMIT ?",
        (args.limit,),
    ).fetchall()
    prepared = []
    for claim_id, claim, cited, evidence_json in claims:
        gold_docs = {f"scifact_{item}" for item in json.loads(cited)}
        evidence = json.loads(evidence_json)
        gold_sentences = set()
        for doc_id, entries in evidence.items():
            for entry in entries:
                for index in entry.get("sentences") or []:
                    gold_sentences.add(f"scifact_{doc_id}_s{index}")
        vector = searcher.vector_search(claim, 20)
        try:
            fts = searcher.fts_search(claim, 20)
        except Exception:
            fts = []
        prepared.append((gold_docs, gold_sentences, vector, fts))
    sent_map = {}
    for para_id, sentence_id in conn.execute("SELECT para_id, sentence_id FROM sentences"):
        sent_map.setdefault(para_id, set()).add(sentence_id)
    conn.close()

    results = {}
    for vw, fw in ((1.0, 1.0), (1.5, 0.5), (1.2, 0.8), (0.8, 1.2), (0.5, 1.5)):
        doc_hits = sent_hits = 0
        rr = []
        for gold_docs, gold_sentences, vector, fts in prepared:
            fused = fuse(vector, fts, vw, fw)
            docs = {item.get("paper_id") for item in fused if item.get("paper_id")}
            if docs & gold_docs:
                doc_hits += 1
                rank = next((i + 1 for i, item in enumerate(fused) if item.get("paper_id") in gold_docs), None)
                if rank:
                    rr.append(1.0 / rank)
            returned_sentences = set()
            for item in fused:
                returned_sentences.update(sent_map.get(item.get("para_id"), set()))
            if returned_sentences & gold_sentences:
                sent_hits += 1
        n = len(prepared)
        results[f"v{vw}_f{fw}"] = {
            "doc_recall@10": round(doc_hits / n, 4),
            "sentence_recall@10": round(sent_hits / n, 4),
            "mrr": round(sum(rr) / n, 4),
        }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(results)



if __name__ == '__main__':
    main()

