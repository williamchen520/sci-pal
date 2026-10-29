"""SciFact claim verification: retrieval + LLM SUPPORT/REFUTE."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))
from services.review.llm_client import create_llm_client

DEFAULT_DB = ROOT / "data" / "benchmark_scifact.db"
DEFAULT_CHROMA = ROOT / "data" / "benchmark_scifact_chroma"
DEFAULT_OUT = ROOT / "eval" / "results" / "scifact_verification_50.json"


def fuse(vector, fts, top_k=5):
    scores = {}
    lookup = {}
    for ranking in (vector, fts):
        for rank, item in enumerate(ranking, 1):
            pid = item.get("para_id")
            if not pid:
                continue
            item.setdefault("paper_id", (item.get("metadata") or {}).get("paper_id"))
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (60 + rank)
            lookup.setdefault(pid, item)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    return [lookup[pid] for pid, _ in ordered]


def label_of(evidence: dict) -> str:
    labels = []
    for entries in evidence.values():
        for entry in entries:
            if entry.get("label"):
                labels.append(entry["label"])
    return "SUPPORT" if labels.count("SUPPORT") >= labels.count("CONTRADICT") else "CONTRADICT"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--oracle", action="store_true")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    import services.search.hybrid_search as hs

    hs.DB_PATH = DEFAULT_DB
    hs.CHROMA_PATH = DEFAULT_CHROMA
    searcher = hs.HybridSearch()
    conn = sqlite3.connect(str(DEFAULT_DB))
    claims = conn.execute(
        "SELECT claim_id, claim, evidence FROM claims ORDER BY claim_id LIMIT ?",
        (args.limit,),
    ).fetchall()
    conn.close()
    llm = create_llm_client()
    rows = []
    correct = 0
    for claim_id, claim, evidence_json in claims:
        gold = label_of(json.loads(evidence_json))
        if args.oracle:
            sentence_ids = []
            for doc_id, entries in json.loads(evidence_json).items():
                for entry in entries:
                    for index in entry.get("sentences") or []:
                        sentence_ids.append(f"scifact_{doc_id}_s{index}")
            if sentence_ids:
                marks = ",".join("?" * len(sentence_ids))
                conn = sqlite3.connect(str(DEFAULT_DB))
                evidence_rows = conn.execute(
                    f"SELECT text FROM sentences WHERE sentence_id IN ({marks})", sentence_ids
                ).fetchall()
                conn.close()
                evidence = "\n\n".join(row[0] for row in evidence_rows)
            else:
                evidence = ""
        else:
            vector = searcher.vector_search(claim, 10)
            try:
                fts = searcher.fts_search(claim, 10)
            except Exception:
                fts = []
            evidence = "\n\n".join(item.get("text", "") for item in fuse(vector, fts, args.top_k))
        prompt = (
            "You are verifying a scientific claim against evidence.\n"
            "Answer with exactly one word: SUPPORT or CONTRADICT.\n"
            "Use only the evidence; if the evidence is insufficient, answer CONTRADICT.\n\n"
            f"Claim: {claim}\n\nEvidence:\n{evidence}"
        )
        try:
            answer = llm.chat(
                system_prompt="You verify scientific claims. Output one word only.",
                user_prompt=prompt,
                temperature=0.0,
            ).strip().upper()
        except Exception as exc:  # noqa: BLE001
            answer = f"ERROR: {exc}"
        if "SUPPORT" in answer:
            prediction = "SUPPORT"
        elif "CONTRADICT" in answer or "REFUTE" in answer:
            prediction = "CONTRADICT"
        else:
            prediction = "OTHER"
        ok = prediction == gold
        correct += int(ok)
        rows.append({"id": claim_id, "claim": claim, "gold": gold, "prediction": prediction, "raw": answer[:80], "ok": ok})
    summary = {
        "claims": len(rows),
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "support": sum(1 for row in rows if row["gold"] == "SUPPORT"),
        "refute": sum(1 for row in rows if row["gold"] == "CONTRADICT"),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
