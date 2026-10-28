"""Stratified QA budget evaluation: simple vs complex, top10 vs top20.

This measures the retrieval layer behind QA (evidence + sufficient signal),
not LLM generation, so it runs quickly and is reproducible.

Usage:
    python eval/qa_budget_eval.py --limit 30 --output eval/results/qa_budget.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from services.qa.budget import is_complex

DEFAULT_GOLD = Path(__file__).resolve().parent / "gold" / "seed.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "results" / "qa_budget.json"


def search(base_url: str, query: str, top_k: int) -> Dict:
    payload = json.dumps({"query": query, "top_k": top_k}).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/evidence/search",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def sentence_ids(payload: Dict) -> List[str]:
    return [
        highlight.get("sentence_id")
        for item in payload.get("evidence") or []
        for highlight in item.get("highlight") or []
        if highlight.get("sentence_id")
    ]


def paragraph_sentence_ids(payload: Dict) -> set:
    return {
        sentence_id
        for item in payload.get("evidence") or []
        for detail in item.get("paragraph_details") or []
        for sentence_id in detail.get("sentence_ids") or []
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    gold = [json.loads(line) for line in Path(args.gold).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        gold = gold[: args.limit]

    results: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(dict))
    counters = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for item in gold:
        stratum = "complex" if is_complex(item["question"]) else "simple"
        expected = set(item.get("evidence") or [])
        for k in (10, 20):
            payload = search(args.base_url, item["question"], k)
            found = sentence_ids(payload)
            counts = counters[stratum][k]
            if expected:
                counts["n"] += 1
                counts["recall"] += len(set(found[:k]) & expected) / len(expected)
                para_sentences = paragraph_sentence_ids(payload)
                counts["paragraph_recall"] += len(expected & para_sentences) / len(expected)
                if payload.get("sufficient"):
                    counts["sufficient"] += 1
            else:
                counts["refusal_n"] += 1
                if not found or payload.get("sufficient") is False:
                    counts["refusal_ok"] += 1

    for stratum in ("simple", "complex"):
        for k in (10, 20):
            counts = counters[stratum][k]
            n = counts.get("n", 0) or 1
            refusal_n = counts.get("refusal_n", 0) or 1
            results[stratum][str(k)] = {
                "questions": int(counts.get("n", 0)),
                "recall@k": round(counts.get("recall", 0) / n, 4) if counts.get("n") else 0.0,
                "paragraph_sentence_recall": round(
                    counts.get("paragraph_recall", 0) / n, 4
                )
                if counts.get("n")
                else 0.0,
                "sufficient_rate": round(counts.get("sufficient", 0) / n, 4)
                if counts.get("n")
                else 0.0,
                "refusal_questions": int(counts.get("refusal_n", 0)),
                "refusal_accuracy": round(counts.get("refusal_ok", 0) / refusal_n, 4)
                if counts.get("refusal_n")
                else None,
            }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
