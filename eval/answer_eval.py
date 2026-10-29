"""Answer evaluation: coverage, forbidden claims, citations, refusal.

Input answers JSONL:
    {"id": "q001", "answer": "... [P1]", "evidence_ids": ["P1"]}

Usage:
    python eval/answer_eval.py --answers eval/answers/sample.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_GOLD = Path(__file__).resolve().parent / "gold" / "seed_100.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent / "results" / "answers.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
CITE_RE = re.compile(r"\[[PFTARG]\d+\]")
REFUSAL_MARKERS = (
    "no relevant", "not found", "insufficient", "does not contain",
    "does not provide", "does not address", "no information", "cannot answer",
    "unable to answer", "not possible", "无法", "未找到", "没有相关",
    "证据不足", "未提及", "没有提供",
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _tokens(text: str) -> set:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if len(token) > 1 or not token.isascii()
    }


def point_covered(point: str, answer: str) -> bool:
    expected = _tokens(point)
    if not expected:
        return True
    return len(expected & _tokens(answer)) / len(expected) >= 0.5


def evaluate(gold: List[Dict[str, Any]], answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {item["id"]: item for item in answers}
    rows = []
    covered_sum = 0.0
    forbidden_hits = 0
    citation_sum = 0
    refusal_total = 0
    refusal_ok = 0
    answered = 0

    for item in gold:
        answer = (by_id.get(item["id"], {}) or {}).get("answer", "")
        points = item.get("answer_points") or []
        if not answer:
            rows.append({"id": item["id"], "missing_answer": True})
            continue
        answered += 1
        covered = sum(1 for point in points if point_covered(point, answer)) / len(points) if points else 1.0
        forbidden = [phrase for phrase in item.get("forbidden") or [] if phrase.lower() in answer.lower()]
        citations = len(CITE_RE.findall(answer))
        covered_sum += covered
        citation_sum += citations
        forbidden_hits += len(forbidden)
        if not points:
            refusal_total += 1
            lowered = answer.lower()
            if any(marker in lowered for marker in REFUSAL_MARKERS):
                refusal_ok += 1
        rows.append(
            {
                "id": item["id"],
                "coverage": round(covered, 4),
                "forbidden": forbidden,
                "citations": citations,
            }
        )

    summary = {
        "answered": answered,
        "coverage": round(covered_sum / answered, 4) if answered else 0.0,
        "forbidden_hits": forbidden_hits,
        "avg_citations": round(citation_sum / answered, 2) if answered else 0.0,
        "refusal_total": refusal_total,
        "refusal_accuracy": round(refusal_ok / refusal_total, 4) if refusal_total else 0.0,
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    result = evaluate(load_jsonl(Path(args.gold)), load_jsonl(Path(args.answers)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
