#!/usr/bin/env python3
"""Build the M2 retrieval benchmark fixture from the local 100-question set."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claims_pilot.yaml"
GOLD = ROOT / "eval" / "gold" / "seed_100.jsonl"
OUT = ROOT / "eval" / "plugins" / "retriever_queries.json"


def main() -> int:
    corpus = yaml.safe_load(CLAIMS.read_text(encoding="utf-8"))["corpus"]
    corpus_set = set(corpus)
    cases = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        paper_ids = [pid for pid in item.get("paper_ids") or [] if pid in corpus_set]
        if not paper_ids:
            continue
        cases.append(
            {
                "case_id": item["id"],
                "query": item["question"],
                "corpus": corpus,
                "gold_paper_ids": paper_ids,
                "gold_sentence_ids": item.get("evidence") or [],
            }
        )
        if len(cases) >= 20:
            break
    OUT.write_text(
        json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print({"cases": len(cases), "corpus": len(corpus), "out": str(OUT)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
