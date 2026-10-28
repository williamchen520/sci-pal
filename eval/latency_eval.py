"""Measure evidence latency for complex questions at top10 vs top20."""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.qa.budget import is_complex

BASE = "http://127.0.0.1:5000"


def search(query: str, top_k: int) -> None:
    request = urllib.request.Request(
        BASE + "/api/evidence/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(request, timeout=300).read()


def main() -> None:
    gold = [
        json.loads(line)
        for line in (ROOT / "eval" / "gold" / "seed_100.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    complex_questions = [item["question"] for item in gold if is_complex(item["question"])][:12]
    if not complex_questions:
        print("no complex questions")
        return
    results = {}
    search(complex_questions[0], 10)  # warmup
    for k in (10, 20):
        times = []
        for question in complex_questions:
            started = time.perf_counter()
            search(question, k)
            times.append((time.perf_counter() - started) * 1000)
        results[k] = {
            "n": len(times),
            "mean_ms": round(statistics.mean(times), 1),
            "median_ms": round(statistics.median(times), 1),
            "p95_ms": round(sorted(times)[max(0, int(len(times) * 0.95) - 1)], 1),
        }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
