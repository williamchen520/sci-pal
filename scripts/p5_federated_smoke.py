"""Small P5 smoke: main + bench federated retrieval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.federated_retriever import FederatedRetriever


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="cancer")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--per-scope-k", type=int, default=20)
    parser.add_argument("--scopes", default="main,bench")
    args = parser.parse_args()
    scopes = [scope.strip() for scope in args.scopes.split(",") if scope.strip()]

    retriever = FederatedRetriever()
    rows = retriever.search(
        args.query,
        top_k=args.top_k,
        per_scope_k=args.per_scope_k,
        scopes=scopes,
    )
    print(f"query={args.query!r} scopes={scopes} rows={len(rows)}")
    for row in rows:
        print(
            f"{row['identity']} score={row['score']:.4f} "
            f"libraries={','.join(row['libraries'])} paper={row['paper_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
