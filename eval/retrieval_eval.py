"""Retrieval evaluation: Recall@k, MRR, nDCG on the gold set.

Usage:
    python eval/retrieval_eval.py --limit 10
    python eval/retrieval_eval.py --base-url http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List

DEFAULT_GOLD = Path(__file__).resolve().parent / "gold" / "seed.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent / "results" / "retrieval.json"


def load_gold(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sentences_from_response(payload: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for item in payload.get("evidence") or []:
        for highlight in item.get("highlight") or []:
            sid = highlight.get("sentence_id")
            if sid:
                out.append(sid)
    return out


def http_search(query: str, top_k: int, base_url: str) -> Dict[str, Any]:
    body = json.dumps({"query": query, "top_k": top_k}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/evidence/search",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _dcg(gains: List[int]) -> float:
    return sum(gain / math.log2(index + 2) for index, gain in enumerate(gains))


def evaluate(
    gold: List[Dict[str, Any]],
    search_fn: Callable[[str, int], Dict[str, Any]],
    top_k: int = 10,
) -> Dict[str, Any]:
    rows = []
    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    counted = 0
    refusal_total = 0
    refusal_ok = 0

    for item in gold:
        expected = set(item.get("evidence") or [])
        payload = search_fn(item["question"], top_k)
        found = _sentences_from_response(payload)

        if not expected:  # refusal / out-of-domain
            refusal_total += 1
            if not found:
                refusal_ok += 1
            rows.append({"id": item["id"], "refusal": True, "returned": len(found)})
            continue

        counted += 1
        ranks = [index for index, sid in enumerate(found[:top_k]) if sid in expected]
        recall = len(set(found[:top_k]) & expected) / len(expected)
        mrr = 1.0 / (ranks[0] + 1) if ranks else 0.0
        gains = [1 if sid in expected else 0 for sid in found[:top_k]]
        ideal = [1] * min(len(expected), top_k)
        ndcg = _dcg(gains) / _dcg(ideal) if _dcg(ideal) else 0.0
        recall_sum += recall
        mrr_sum += mrr
        ndcg_sum += ndcg
        rows.append(
            {
                "id": item["id"],
                "recall": round(recall, 4),
                "mrr": round(mrr, 4),
                "ndcg": round(ndcg, 4),
                "gold": len(expected),
                "returned": len(found),
                "hit_rank": ranks[0] + 1 if ranks else None,
            }
        )

    summary = {
        "questions": counted,
        f"recall@{top_k}": round(recall_sum / counted, 4) if counted else 0.0,
        "mrr": round(mrr_sum / counted, 4) if counted else 0.0,
        f"ndcg@{top_k}": round(ndcg_sum / counted, 4) if counted else 0.0,
        "refusal_total": refusal_total,
        "refusal_accuracy": round(refusal_ok / refusal_total, 4) if refusal_total else 0.0,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    gold = load_gold(Path(args.gold))
    if args.limit:
        gold = gold[: args.limit]
    result = evaluate(gold, lambda q, k: http_search(q, k, args.base_url), args.top_k)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
