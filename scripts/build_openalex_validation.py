#!/usr/bin/env python3
"""Build a stratified 100-paper sample for OpenAlex label validation."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Proportional target, with one reserved slot each for rare domains.
TARGET = {
    "Health Sciences": 59,
    "Life Sciences": 35,
    "Physical Sciences": 4,
    "Social Sciences": 1,
    "(unknown)": 1,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", default=str(ROOT / "eval" / "results" / "openalex_coverage.json"))
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--out", default=str(ROOT / "eval" / "validation" / "openalex_100.csv"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    rows = list((coverage.get("rows") or {}).items())
    by_domain = {}
    for paper_id, row in rows:
        domain = row.get("domain_name") or "(unknown)"
        by_domain.setdefault(domain, []).append((paper_id, row))

    rng = random.Random(args.seed)
    selected = []
    for domain, target in TARGET.items():
        pool = by_domain.get(domain, [])
        if not pool:
            continue
        take = min(target, len(pool))
        selected.extend(rng.sample(pool, take))
    # Fill to 100 if a small domain was short.
    seen = {paper_id for paper_id, _ in selected}
    if len(selected) < 100:
        remaining = [(paper_id, row) for paper_id, row in rows if paper_id not in seen]
        selected.extend(rng.sample(remaining, min(100 - len(selected), len(remaining))))
    selected = selected[:100]

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out_rows = []
    for index, (paper_id, row) in enumerate(sorted(selected, key=lambda item: item[0]), start=1):
        paper = db.execute(
            "SELECT paper_id, doi, title, journal, year, paper_type, abstract FROM papers WHERE paper_id = ?",
            (paper_id,),
        ).fetchone()
        auto = db.execute(
            "SELECT domain_id, confidence FROM paper_domains WHERE paper_id = ? AND source = 'auto'",
            (paper_id,),
        ).fetchone()
        if not paper:
            continue
        out_rows.append(
            {
                "sample_id": f"OA{index:03d}",
                "paper_id": paper["paper_id"],
                "doi": paper["doi"],
                "title": paper["title"],
                "journal": paper["journal"],
                "year": paper["year"],
                "paper_type": paper["paper_type"],
                "openalex_domain": row.get("domain_name"),
                "openalex_field": row.get("field_name"),
                "openalex_subfield": row.get("subfield_name"),
                "openalex_topic": row.get("topic_name"),
                "auto_domain_l1": auto["domain_id"] if auto else "",
                "auto_confidence": round(auto["confidence"], 4) if auto and auto["confidence"] is not None else "",
                "abstract_snippet": (paper["abstract"] or "")[:600].replace("\n", " "),
                "human_domain": "",
                "human_topic_match": "",
                "human_notes": "",
            }
        )
    db.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    counts = Counter(row["openalex_domain"] for row in out_rows)
    print(json.dumps({"out": str(out_path), "rows": len(out_rows), "domains": counts, "seed": args.seed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
