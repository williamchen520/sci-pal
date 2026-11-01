#!/usr/bin/env python3
"""Profile one query through the RRF stages with an isolated reranker worker."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_rrf_compare import (  # noqa: E402
    load_paragraph_texts,
    paragraph_candidates,
)
from services.search.rerank_worker import RerankWorker  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--query", default="What is ICI rechallenge in hepatocellular carcinoma?")
    parser.add_argument("--candidates", type=int, default=20)
    parser.add_argument("--sentence-depth", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")

    import psycopg

    timings = {}
    t0 = time.perf_counter()
    sentence_fts = SentenceFTS(args.pg_dsn)
    t1 = time.perf_counter()
    timings["fts_init"] = t1 - t0

    hits = sentence_fts.search(args.query, top_k=args.sentence_depth)
    t2 = time.perf_counter()
    timings["sentence_search"] = t2 - t1
    timings["sentence_hits"] = len(hits)

    candidates = paragraph_candidates(hits, args.candidates)
    t3 = time.perf_counter()
    timings["paragraph_aggregate"] = t3 - t2
    timings["paragraphs"] = len(candidates)

    with psycopg.connect(args.pg_dsn) as pg:
        texts = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
    t4 = time.perf_counter()
    timings["paragraph_text_load"] = t4 - t3

    t5 = time.perf_counter()
    worker = RerankWorker(timeout=max(args.timeout, 60.0))
    timings["worker_start"] = time.perf_counter() - t5

    t6 = time.perf_counter()
    scores = worker.score(
        args.query,
        [(texts.get(c["para_id"]) or c["text"])[:512] for c in candidates],
        batch_size=args.batch_size,
        timeout=args.timeout,
    )
    t7 = time.perf_counter()
    timings["rerank_score"] = t7 - t6
    timings["scores"] = len(scores)
    worker.close()
    timings["total"] = t7 - t0

    text = json.dumps(timings, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
