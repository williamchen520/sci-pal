"""Audit citation coverage and refusal on a sample of gold questions."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.qa.verify import verify_answer

CITE_RE = re.compile(r"\[([PFTARG])(\d+)\]")
REFUSAL_MARKERS = ("does not contain", "does not provide", "no information", "cannot answer", "insufficient")


def post(base: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def ask(base: str, question: str, timeout: int = 900) -> dict:
    task_id = post(base, "/api/qa/ask_async", {"question": question})["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = get(base, f"/api/review/task/{task_id}")
        if task.get("status") == "completed":
            return task.get("result") or {}
        if task.get("status") in {"failed", "cancelled"}:
            raise RuntimeError(task.get("error") or task.get("status"))
        time.sleep(5)
    raise TimeoutError(task_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(ROOT / "eval" / "gold" / "seed_100.jsonl"))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "citation_audit_20.json"))
    args = parser.parse_args()

    gold = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # keep refusal questions and take the rest from the first questions
    selected = [item for item in gold if item.get("category") == "refusal"]
    selected += [item for item in gold if item.get("category") != "refusal"][: args.limit - len(selected)]

    rows = []
    for item in selected:
        result = ask(args.base_url, item["question"])
        citations = result.get("citations") or []
        cited_ids = {f"[{cite['raw'].strip('[]')}]" if isinstance(cite, dict) else str(cite) for cite in citations}
        source_ids = set()
        allowed_ids = set()
        cited_sources = []
        for source in (result.get("sources") or {}).get("paragraphs") or []:
            citation_id = source.get("citation_id") or ""
            if citation_id:
                allowed_ids.add(citation_id)
            if citation_id and citation_id in cited_ids:
                cited_sources.append(source)
                source_ids.update(source.get("sentence_ids") or [])
        gold_ids = set(item.get("evidence") or [])
        overlap = source_ids & gold_ids
        paragraph_hits = sum(
            1
            for source in cited_sources
            if set(source.get("sentence_ids") or []) & gold_ids
        )
        verification = verify_answer(
            result.get("answer") or "",
            evidence_ids=[f"P{i}" for i in range(1, len((result.get("sources") or {}).get("paragraphs") or []) + 1)],
        )
        rows.append(
            {
                "id": item["id"],
                "category": item.get("category"),
                "question": item["question"],
                "citations": len(citations),
                "unknown_citations": sorted(cited_ids - allowed_ids),
                "cited_sentence_ids": len(source_ids),
                "gold_sentence_ids": len(gold_ids),
                "paragraph_citation_precision": round(paragraph_hits / len(cited_sources), 4) if cited_sources else 0.0,
                "sentence_recall": round(len(overlap) / len(gold_ids), 4) if gold_ids else 0.0,
                "refused": any(
                    marker in (result.get("answer") or "")[:250].lower()
                    for marker in REFUSAL_MARKERS
                ),
                "gold_hit": bool(overlap),
                "answer_status": result.get("answer_status"),
                "uncited_claims": len(verification.get("uncited_claims") or []),
                "quote_mismatch": len(verification.get("quote_mismatch") or []),
            }
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print({
        "questions": len(rows),
        "avg_citations": round(sum(row["citations"] for row in rows) / len(rows), 2),
        "avg_paragraph_citation_precision": round(sum(row["paragraph_citation_precision"] for row in rows) / len(rows), 4),
        "avg_sentence_recall": round(sum(row["sentence_recall"] for row in rows) / len(rows), 4),
        "gold_hit_rate": round(sum(1 for row in rows if row["gold_hit"]) / len(rows), 4),
        "refusal_ok": sum(1 for row in rows if row["category"] == "refusal" and row["refused"]),
        "refusal_total": sum(1 for row in rows if row["category"] == "refusal"),
        "uncited_total": sum(row["uncited_claims"] for row in rows),
        "saved": str(output),
    })
    for row in rows:
        print(row["id"], row["category"], row["citations"], row["paragraph_citation_precision"], row["sentence_recall"], row["refused"], row["gold_hit"])


if __name__ == "__main__":
    main()
