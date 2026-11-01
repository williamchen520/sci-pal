#!/usr/bin/env python3
"""Query the source-aware sentence FTS in scipal_v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.search.sentence_fts import SentenceFTS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default="")
    parser.add_argument("--query", required=True)
    parser.add_argument("--source-type", choices=("xml", "pdf", "all"), default="all")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    dsn = args.dsn
    if not dsn:
        raise SystemExit("--dsn is required")
    if "scipal_v2" not in dsn:
        raise SystemExit("refusing to read a non-scipal_v2 database")
    hits = SentenceFTS(dsn).search(
        args.query,
        top_k=args.top_k,
        source_type=None if args.source_type == "all" else args.source_type,
    )
    payload = {
        "query": args.query,
        "count": len(hits),
        "hits": [hit.as_dict() for hit in hits],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
