"""Library-scoped code search evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

from code_rag.search import MODEL, search


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default=str(Path(__file__).with_name("queries.json")))
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    cases = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    model = SentenceTransformer(MODEL, device="cuda")
    hit1 = hit5 = 0
    rows = []
    for case in cases:
        hits = search(case["query"], library_id=case["library_id"], top_k=5, model=model)
        rank = next((i for i, hit in enumerate(hits, 1) if hit["symbol_name"] == case["expected"]), None)
        hit1 += int(rank == 1)
        hit5 += int(rank is not None and rank <= 5)
        rows.append({"query": case["query"], "rank": rank, "top": [hit["symbol_name"] for hit in hits[:3]]})
    n = len(cases)
    result = {"queries": n, "hit@1": hit1 / n, "hit@5": hit5 / n, "rows": rows}
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
