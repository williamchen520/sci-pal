"""Async end-to-end QA answer evaluation."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.answer_eval import evaluate as evaluate_answers

DEFAULT_GOLD = ROOT / "eval" / "gold" / "seed_100.jsonl"


def post(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def ask_async(base_url: str, question: str, timeout: int) -> dict:
    task_id = post(base_url, "/api/qa/ask_async", {"question": question})["task_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = get(base_url, f"/api/review/task/{task_id}")
        status = task.get("status")
        if status == "completed":
            return task.get("result") or {}
        if status in {"failed", "cancelled"}:
            raise RuntimeError(task.get("error") or status)
        time.sleep(10)
    raise TimeoutError(f"task {task_id} exceeded {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default=str(DEFAULT_GOLD))
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "qa_answers_async.json"))
    args = parser.parse_args()

    gold = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][: args.limit]
    answers = []
    for item in gold:
        start = time.time()
        response = ask_async(args.base_url, item["question"], args.timeout)
        answers.append(
            {
                "id": item["id"],
                "answer": response.get("answer") or "",
                "evidence_ids": [cite.get("raw") for cite in response.get("citations") or []],
                "citation_fallback": response.get("citation_fallback", False),
                "elapsed_s": round(time.time() - start, 1),
            }
        )
    result = evaluate_answers(gold, answers)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"summary": result["summary"], "answers": answers}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print("elapsed:", [item["elapsed_s"] for item in answers])
    print(f"saved: {output}")


if __name__ == "__main__":
    main()
