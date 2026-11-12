"""Compare vector-only, lexical-only and hybrid retrieval on docs/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

from docs_rag.search import MODEL, MODES, search


def run_mode(cases, *, mode: str, top_k: int, model: SentenceTransformer) -> dict:
    hits_at_1 = hits_at_5 = hits_at_10 = 0
    reciprocal = 0.0
    rows = []
    for case in cases:
        hits = search(case["query"], top_k=top_k, model=model, mode=mode)
        rank = next(
            (
                index
                for index, hit in enumerate(hits, 1)
                if case["expected"] in hit["path"]
            ),
            None,
        )
        hits_at_1 += int(rank == 1)
        hits_at_5 += int(rank is not None and rank <= 5)
        hits_at_10 += int(rank is not None and rank <= 10)
        reciprocal += 1.0 / rank if rank else 0.0
        rows.append(
            {
                "query": case["query"],
                "expected": case["expected"],
                "rank": rank,
                "top": [
                    {"path": hit["path"], "title": hit["title"], "score": hit["score"]}
                    for hit in hits[:3]
                ],
            }
        )
    n = len(cases)
    return {
        "mode": mode,
        "queries": n,
        "hit@1": hits_at_1 / n,
        "hit@5": hits_at_5 / n,
        "hit@10": hits_at_10 / n,
        "mrr@10": reciprocal / n,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default=str(Path(__file__).with_name("eval_queries.json")))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--modes", default="vector,lexical,hybrid")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)

    cases = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown = set(modes) - MODES
    if unknown:
        raise SystemExit(f"unknown modes: {sorted(unknown)}")
    model = SentenceTransformer(MODEL, device="cuda")
    results = {mode: run_mode(cases, mode=mode, top_k=args.top_k, model=model) for mode in modes}
    output = {"queries": len(cases), "results": results}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
