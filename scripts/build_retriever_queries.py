#!/usr/bin/env python3
"""Build the M2 retrieval benchmark fixture.

Sources (deterministic, no LLM):
1. local seed_100 questions whose gold paper is in the 32-paper HCC corpus;
2. 20 cross-topic seed questions with non-HCC gold papers;
3. claim-derived queries from qualifiers + supporting evidence paper ids;
4. paper-title queries for corpus papers that have sentences.

The corpus is expanded to 100 papers (HCC + cross-topic gold + distractors) so
lexical overlap alone is not enough. This is a benchmark fixture, not a gold
clinical claim set.
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
TARGET_CROSS_TOPIC = 20
TARGET_CORPUS = 100


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


def _has_sentences(conn: sqlite3.Connection, paper_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sentences WHERE paper_id = ? LIMIT 1", (paper_id,)
    ).fetchone() is not None


def main() -> int:
    claims_data = yaml.safe_load(CLAIMS.read_text(encoding="utf-8"))
    corpus = list(claims_data["corpus"])
    corpus_set = set(corpus)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    seed_rows = [
        json.loads(line)
        for line in GOLD.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    hcc_cases = []
    cross_cases = []
    for item in seed_rows:
        gold = [pid for pid in item.get("paper_ids") or [] if _has_sentences(conn, pid)]
        if not gold:
            continue
        in_hcc = [pid for pid in gold if pid in corpus_set]
        case = {
            "case_id": item["id"],
            "query": item["question"],
            "gold_paper_ids": gold,
            "gold_sentence_ids": item.get("evidence") or [],
            "category": item.get("category") or "factual",
            "difficulty": item.get("difficulty") or "medium",
        }
        if in_hcc:
            hcc_cases.append({**case, "gold_paper_ids": in_hcc, "source": "seed_100"})
        elif len(cross_cases) < TARGET_CROSS_TOPIC:
            cross_cases.append({**case, "source": "cross_topic"})

    # Build a 100-paper corpus: HCC + cross-topic gold + deterministic distractors.
    mixed = list(corpus)
    for case in cross_cases:
        for paper_id in case["gold_paper_ids"]:
            if paper_id not in mixed:
                mixed.append(paper_id)
    marks = ",".join("?" * len(mixed)) if mixed else "''"
    distractors = conn.execute(
        f"""
        SELECT DISTINCT p.paper_id
        FROM papers p JOIN sentences s ON s.paper_id = p.paper_id
        WHERE p.paper_id NOT IN ({marks})
        ORDER BY p.paper_id
        LIMIT ?
        """,
        [*mixed, max(0, TARGET_CORPUS - len(mixed))],
    ).fetchall()
    for row in distractors:
        if len(mixed) >= TARGET_CORPUS:
            break
        mixed.append(row["paper_id"])
    mixed = mixed[:TARGET_CORPUS]

    cases: list[dict] = []
    for case in hcc_cases:
        cases.append({**case, "corpus": mixed})
    for case in cross_cases:
        cases.append({**case, "corpus": mixed})

    # Claim-derived queries: qualifier terms + evidence paper ids.
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
                    "corpus": mixed,
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

    # Title queries for HCC corpus papers with sentence data.
    title_cases = 0
    for paper_id in corpus:
        if title_cases >= TARGET_TITLE_QUERIES:
            break
        row = conn.execute(
            "SELECT title FROM papers WHERE paper_id = ?", (paper_id,)
        ).fetchone()
        if not row or not row["title"] or not _has_sentences(conn, paper_id):
            continue
        cases.append(
            {
                "case_id": f"title_{paper_id[-12:]}",
                "query": str(row["title"]),
                "corpus": mixed,
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
            "corpus": len(mixed),
            "by_source": by_source,
            "out": str(OUT),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
