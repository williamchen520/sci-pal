#!/usr/bin/env python3
"""End-to-end profile of the 20-query RRF loop against the warm reranker service."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_rrf_compare import load_paragraph_texts, paragraph_candidates  # noqa: E402
from scripts.fts_sentence_compare import load_cases  # noqa: E402
from services.search.rerank_client import RerankClient  # noqa: E402
from services.search.sentence_fts import SentenceFTS  # noqa: E402


def _stats(values):
    if not values:
        return None
    return {
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default="")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--per-source", type=int, default=5)
    parser.add_argument("--counts", default="20,50")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not args.pg_dsn:
        raise SystemExit("--pg-dsn is required")
    if not RerankClient(args.url).health():
        raise SystemExit(f"reranker service is not healthy: {args.url}")

    counts = [int(value) for value in args.counts.split(",") if value.strip()]
    cases = load_cases(ROOT / "eval" / "plugins" / "retriever_queries.json", args.per_source)
    sentence_fts = SentenceFTS(args.pg_dsn)
    rows = []
    for case in cases:
        row = {"case_id": case["case_id"], "query": case["query"]}
        started = time.perf_counter()
        hits = sentence_fts.search(case["query"], top_k=1000)
        row["sentence_search"] = time.perf_counter() - started
        started = time.perf_counter()
        candidates = paragraph_candidates(hits, max(counts))
        row["aggregate"] = time.perf_counter() - started
        started = time.perf_counter()
        texts = load_paragraph_texts(args.pg_dsn, [c["para_id"] for c in candidates])
        row["text_load"] = time.perf_counter() - started
        row["scores"] = {}
        for count in counts:
            batch = [
                (texts.get(c["para_id"]) or c["text"])[:512]
                for c in candidates[:count]
            ]
            started = time.perf_counter()
            RerankClient(args.url).score(
                case["query"], batch, batch_size=8, timeout=60
            )
            row["scores"][str(count)] = time.perf_counter() - started
        rows.append(row)
        print(
            f"[{case['case_id']}] fts={row['sentence_search']:.3f}s "
            f"text={row['text_load']:.3f}s "
            f"score20={row['scores']['20']:.3f}s score50={row['scores']['50']:.3f}s",
            file=sys.stderr,
            flush=True,
        )

    summary = {
        "queries": len(rows),
        "sentence_search": _stats([row["sentence_search"] for row in rows]),
        "aggregate": _stats([row["aggregate"] for row in rows]),
        "text_load": _stats([row["text_load"] for row in rows]),
        "score20": _stats([row["scores"]["20"] for row in rows]),
        "score50": _stats([row["scores"]["50"] for row in rows]),
        "total_mean": round(
            sum(
                row["sentence_search"]
                + row["aggregate"]
                + row["text_load"]
                + row["scores"]["20"]
                + row["scores"]["50"]
                for row in rows
            ),
            3,
        ),
    }
    output = {"url": args.url, "summary": summary, "rows": rows}
    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
