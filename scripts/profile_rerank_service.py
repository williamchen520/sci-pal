#!/usr/bin/env python3
"""Measure `/score` latency for 20 and 50 real paragraphs through the warm service."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_rrf_compare import load_paragraph_texts, paragraph_candidates  # noqa: E402
from services.search.rerank_client import RerankClient  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--query", default="What is ICI rechallenge in hepatocellular carcinoma?")
    parser.add_argument("--counts", default="20,50")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if not RerankClient(args.url).health():
        raise SystemExit(f"reranker service is not healthy: {args.url}")

    sentence_fts = SentenceFTS(args.pg_dsn)
    hits = sentence_fts.search(args.query, top_k=1000)
    counts = [int(value) for value in args.counts.split(",") if value.strip()]
    max_count = max(counts)
    candidates = paragraph_candidates(hits, max_count)
    texts_by_id = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
    results = []
    for count in counts:
        texts = [
            (texts_by_id.get(c["para_id"]) or c["text"])[:512]
            for c in candidates[:count]
        ]
        samples = []
        for run in range(args.repeat):
            started = time.perf_counter()
            scores = RerankClient(args.url).score(args.query, texts, batch_size=8, timeout=60)
            elapsed = time.perf_counter() - started
            samples.append(elapsed)
            if len(scores) != len(texts):
                raise RuntimeError("score count mismatch")
        results.append(
            {
                "paragraphs": count,
                "runs": [round(value, 4) for value in samples],
                "mean": round(sum(samples) / len(samples), 4),
                "min": round(min(samples), 4),
                "max": round(max(samples), 4),
            }
        )
    output = {
        "url": args.url,
        "query": args.query,
        "sentence_hits": len(hits),
        "results": results,
    }
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
