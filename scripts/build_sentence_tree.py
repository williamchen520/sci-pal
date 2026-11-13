#!/usr/bin/env python3
"""Populate sentence rows for one paper from existing paragraphs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.papers.sentences import build_for_paper


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paper_id")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_OWNER_DSN", ""))
    parser.add_argument("--no-replace", action="store_true")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_PG_OWNER_DSN or --dsn is required")
    result = build_for_paper(
        paper_id=args.paper_id,
        dsn=args.dsn,
        replace=not args.no_replace,
    )
    print(f"SENTENCE_TREE_OK paper={args.paper_id} paragraphs={result['paragraphs']} sentences={result['sentences']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
