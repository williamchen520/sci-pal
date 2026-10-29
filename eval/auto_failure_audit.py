"""Audit low-coverage auto questions: retrieval hit vs evaluation/gold issue."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.answer_eval import evaluate


def retrieval_papers(base_url: str, question: str, top_k: int = 10) -> list[str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/evidence/search",
        data=json.dumps({"query": question, "top_k": top_k}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [entry.get("paper", {}).get("paper_id", "") for entry in payload.get("evidence", [])]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(ROOT / "eval" / "gold" / "seed_100.jsonl"))
    parser.add_argument("--answers", default=str(ROOT / "eval" / "results" / "qa_cloud_100.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "auto_failure_audit.json"))
    args = parser.parse_args()

    gold = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    answers = json.loads(Path(args.answers).read_text(encoding="utf-8"))["answers"]
    result = evaluate(gold, answers)
    rows = {row["id"]: row for row in result["rows"]}
    items = sorted(
        [item for item in gold if item.get("category") == "auto"],
        key=lambda item: rows.get(item["id"], {}).get("coverage", 0.0),
    )[: args.limit]

    audit = []
    for item in items:
        returned = set(retrieval_papers(args.base_url, item["question"]))
        gold_papers = set(item.get("paper_ids") or [])
        audit.append(
            {
                "id": item["id"],
                "question": item["question"],
                "coverage": rows.get(item["id"], {}).get("coverage", 0.0),
                "retrieval_hit": bool(returned & gold_papers),
                "answer_points": item.get("answer_points"),
                "gold_papers": sorted(gold_papers),
            }
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    hit = sum(1 for item in audit if item["retrieval_hit"])
    print({"items": len(audit), "retrieval_hit": hit, "saved": str(output)})
    for item in audit:
        print(item["id"], item["coverage"], item["retrieval_hit"])


if __name__ == "__main__":
    main()
