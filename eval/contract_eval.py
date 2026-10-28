"""Contract-level evaluation: sentence vs paragraph evidence units.

Usage:
    python -m eval.contract_eval --limit 30
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_GOLD = ROOT / "eval" / "gold" / "seed.jsonl"
DEFAULT_OUTPUT = ROOT / "eval" / "results" / "contract.json"
DEFAULT_DB = ROOT / "data" / "research.db"


def search(base_url: str, query: str, top_k: int) -> Dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/evidence/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def strict_sentences(payload: Dict, top_k: int) -> List[str]:
    return [
        highlight.get("sentence_id")
        for item in payload.get("evidence") or []
        for highlight in item.get("highlight") or []
        if highlight.get("sentence_id")
    ][:top_k]


def paragraph_sentences(payload: Dict) -> Set[str]:
    return {
        sentence_id
        for item in payload.get("evidence") or []
        for detail in item.get("paragraph_details") or []
        for sentence_id in detail.get("sentence_ids") or []
    }


def evaluate(gold: List[Dict], base_url: str, top_k: int, section_of, paragraph_of) -> Dict:
    strict_sum = 0.0
    paragraph_sum = 0.0
    sent_in_para_sum = 0.0
    counted = 0
    refusal_total = 0
    refusal_ok = 0
    for item in gold:
        expected = set(item.get("evidence") or [])
        payload = search(base_url, item["question"], top_k)
        if not expected:
            refusal_total += 1
            if payload.get("sufficient") is False or not strict_sentences(payload, top_k):
                refusal_ok += 1
            continue
        counted += 1
        strict = strict_sentences(payload, top_k)
        paragraph_sents = paragraph_sentences(payload)
        expected_paras = {paragraph_of(sid) for sid in expected if paragraph_of(sid)}
        returned_paras = {paragraph_of(sid) for sid in strict if paragraph_of(sid)}
        strict_sum += len(set(strict) & expected) / len(expected)
        paragraph_sum += (
            len(expected_paras & returned_paras) / len(expected_paras)
            if expected_paras
            else 0.0
        )
        sent_in_para_sum += len(expected & paragraph_sents) / len(expected)
    return {
        "top_k": top_k,
        "questions": counted,
        "strict_sentence_recall": round(strict_sum / counted, 4) if counted else 0.0,
        "paragraph_recall": round(paragraph_sum / counted, 4) if counted else 0.0,
        "sentence_in_returned_paragraphs": round(sent_in_para_sum / counted, 4) if counted else 0.0,
        "refusal_accuracy": round(refusal_ok / refusal_total, 4) if refusal_total else 0.0,
    }


def markdown(result: Dict) -> str:
    lines = [
        "| 预算 | questions | sentence Recall | paragraph Recall | sentence-in-paragraphs | refusal |",
        "|---|---|---|---|---|---|",
    ]
    for k in ("10", "20"):
        row = result[k]
        lines.append(
            f"| top{k} | {row['questions']} | {row['strict_sentence_recall']} | "
            f"{row['paragraph_recall']} | {row['sentence_in_returned_paragraphs']} | "
            f"{row['refusal_accuracy']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    gold = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        gold = gold[: args.limit]

    conn = sqlite3.connect(str(DEFAULT_DB))
    cache: Dict[str, Dict[str, str]] = {}

    def lookup(sentence_id: str) -> Dict[str, str]:
        if sentence_id not in cache:
            row = conn.execute(
                "SELECT section_id, para_id FROM sentences WHERE sentence_id = ?",
                (sentence_id,),
            ).fetchone()
            cache[sentence_id] = {"section": row[0] if row else None, "para": row[1] if row else None}
        return cache[sentence_id]

    section_of = lambda sid: lookup(sid)["section"]
    paragraph_of = lambda sid: lookup(sid)["para"]

    result = {}
    for top_k in (10, 20):
        result[str(top_k)] = evaluate(gold, args.base_url, top_k, section_of, paragraph_of)
    conn.close()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(markdown(result))
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
