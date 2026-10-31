#!/usr/bin/env python3
"""Build the M2 retrieval benchmark fixture.

Sources (deterministic, no LLM):
1. local seed_100 questions whose gold paper is in the 32-paper corpus;
2. claim-derived queries from qualifiers + supporting evidence paper ids;
3. paper-title queries for corpus papers that have sentences.

The fixture is designed to cover easy/medium/hard and claim/title/factual
queries, not to make any retriever look good.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "packs" / "biomed-oncoimmuno" / "eval" / "claims_pilot.yaml"
GOLD = ROOT / "eval" / "gold" / "seed_100.jsonl"
DB = ROOT / "data" / "research.db"
OUT = ROOT / "eval" / "plugins" / "retriever_queries.json"

TARGET_CLAIM_QUERIES = 20
TARGET_TITLE_QUERIES = 20


def _dedupe(cases: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for case in cases:
        key = case["query"].strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(case)
    return result


def main() -> int:
    claims_data = yaml.safe_load(CLAIMS.read_text(encoding="utf-8"))
    corpus = claims_data["corpus"]
    corpus_set = set(corpus)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cases: list[dict] = []

    # 1) seed questions with at least one gold paper in the fixed corpus
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
                "category": item.get("category") or "factual",
                "difficulty": item.get("difficulty") or "medium",
                "source": "seed_100",
            }
        )

    # 2) claim-derived queries: qualifier terms + evidence paper ids
    claim_cases = 0
    for claim in claims_data.get("claims") or []:
        evidence_papers = []
        for item in claim.get("evidence") or []:
            row = conn.execute(
                "SELECT paper_id FROM sentences WHERE sentence_id = ?",
                (item.get("sentence_id"),),
            ).fetchone()
            if row and row["paper_id"] in corpus_set and row["paper_id"] not in evidence_papers:
                evidence_papers.append(row["paper_id"])
        if not evidence_papers:
            continue
        qualifiers = claim.get("qualifiers") or {}
        variants = [
            " ".join(
                str(qualifiers.get(key) or "")
                for key in ("population", "intervention", "outcome")
            ),
            " ".join(
                str(qualifiers.get(key) or "")
                for key in ("intervention", "comparator", "outcome")
            ),
        ]
        for index, query in enumerate(variants):
            query = " ".join(query.split())
            if not query:
                continue
            cases.append(
                {
                    "case_id": f"{claim['claim_id']}__q{index + 1}",
                    "query": query,
                    "corpus": corpus,
                    "gold_paper_ids": evidence_papers,
                    "gold_sentence_ids": [
                        item["sentence_id"] for item in claim.get("evidence") or []
                    ],
                    "category": "claim",
                    "difficulty": "hard" if index else "medium",
                    "source": "claim_qualifiers",
                }
            )
            claim_cases += 1
        if claim_cases >= TARGET_CLAIM_QUERIES:
            break

    # 3) title queries for corpus papers with sentence data
    title_cases = 0
    for paper_id in corpus:
        if title_cases >= TARGET_TITLE_QUERIES:
            break
        row = conn.execute(
            "SELECT title FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM sentences WHERE paper_id = ?", (paper_id,)
        ).fetchone()[0]
        if not row or not row["title"] or count == 0:
            continue
        cases.append(
            {
                "case_id": f"title_{paper_id[-12:]}",
                "query": str(row["title"]),
                "corpus": corpus,
                "gold_paper_ids": [paper_id],
                "gold_sentence_ids": [],
                "category": "title",
                "difficulty": "easy",
                "source": "paper_title",
            }
        )
        title_cases += 1

    conn.close()
    cases = _dedupe(cases)
    OUT.write_text(
        json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    by_source = {}
    for case in cases:
        by_source[case["source"]] = by_source.get(case["source"], 0) + 1
    print(
        {
            "cases": len(cases),
            "corpus": len(corpus),
            "by_source": by_source,
            "out": str(OUT),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
