"""Evaluate sentence-window hybrid retrieval on the 20-question gold set."""

from __future__ import annotations

import argparse
import json
import os
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.determinism import seed_everything
from services.search.sentence_hybrid import SentenceHybridRetriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--gold", default=str(ROOT / "eval" / "gold" / "seed_100.jsonl"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rerank-pool", type=int, default=100)
    parser.add_argument("--sent-k", type=int, default=200)
    parser.add_argument("--max-full-chars", type=int, default=600)
    parser.add_argument("--output", default=str(ROOT / "eval" / "results" / "sentence_window_20.json"))
    args = parser.parse_args()
    seed_everything(42)

    gold = [
        json.loads(line)
        for line in Path(args.gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][: args.limit]

    retriever = SentenceHybridRetriever(rerank_pool=args.rerank_pool, sentence_top_k=args.sent_k, max_full_chars=args.max_full_chars)
    rows = []
    for item in gold:
        expected = set(item.get("evidence") or [])
        started = time.time()
        units = retriever.search(item["question"], top_k=args.top_k)
        elapsed = time.time() - started
        ids = [unit["sentence_id"] for unit in units]
        modes = [unit["context_mode"] for unit in units]
        chars = [len(unit.get("text") or "") for unit in units]
        rows.append(
            {
                "id": item["id"],
                "question": item["question"],
                "sec": round(elapsed, 2),
                "hit": bool(expected & set(ids)),
                "top10": ids,
                "context_modes": modes,
                "context_chars": sum(chars),
                "expected": sorted(expected),
            }
        )
        print(f"{item['id']} {elapsed:.1f}s hit={rows[-1]['hit']} modes={modes[:3]} chars={sum(chars)}")

    summary = {
        "n": len(rows),
        "recall@10": round(sum(row["hit"] for row in rows) / len(rows), 4),
        "sec_avg": round(sum(row["sec"] for row in rows) / len(rows), 2),
        "context_chars_avg": round(sum(row["context_chars"] for row in rows) / len(rows), 1),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("saved", output)


if __name__ == "__main__":
    main()
