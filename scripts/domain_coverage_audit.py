#!/usr/bin/env python3
"""Proxy domain-coverage audit.

No reliable L1/L2 domain labels exist in the current SQLite database, so this
audit reports:

* corpus long-tail distribution by journal;
* lexical query support as an upper-bound proxy for available relevant papers;
* result hubness from an existing paraphrase audit JSON.

It explicitly reports `domain_labels: missing` instead of inventing domains.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.fts_sentence_compare import load_cases, terms_for  # noqa: E402


def entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts if c > 0)


def gini(counts: list[int]) -> float:
    values = sorted(counts)
    total = sum(values)
    if total <= 0 or len(values) < 2:
        return 0.0
    n = len(values)
    cumulative = 0.0
    for i, value in enumerate(values, 1):
        cumulative += i * value
    return (2 * cumulative) / (n * total) - (n + 1) / n


def load_labels(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {
            row["paper_id"]: {
                "domain_l1": row.get("domain_l1", ""),
                "domain_l2": row.get("domain_l2", ""),
            }
            for row in reader
            if row.get("paper_id")
        }


def corpus_stats(conn, labels: dict[str, dict[str, str]]) -> dict:
    rows = conn.execute("SELECT paper_id, journal, year, paper_type FROM papers").fetchall()
    journals = Counter((row[1] or "(none)") for row in rows)
    years = Counter((row[2] or "(none)") for row in rows)
    types = Counter((row[3] or "(none)") for row in rows)
    counts = list(journals.values())
    top = journals.most_common(10)
    panel = Counter(
        labels[row[0]]["domain_l1"] for row in rows if row[0] in labels
    )
    return {
        "papers": len(rows),
        "journals": len(journals),
        "journal_entropy": round(entropy(counts), 3),
        "journal_gini": round(gini(counts), 3),
        "top_journal_share": round(top[0][1] / len(rows), 3) if top and rows else 0,
        "top_journals": top,
        "singleton_journals": sum(1 for count in counts if count == 1),
        "years": years.most_common(10),
        "paper_types": types.most_common(10),
        "domain_labels": "present" if labels else "missing",
        "labelled_papers": len(labels),
        "domain_counts": panel.most_common(20),
    }


def query_support(conn, cases, labels) -> list[dict]:
    out = []
    for case in cases:
        terms = terms_for(case["query"])
        gold_id = (case.get("gold_paper_ids") or [""])[0]
        gold_domain = labels.get(gold_id, {}).get("domain_l1")
        domain_available = (
            sum(1 for value in labels.values() if value.get("domain_l1") == gold_domain)
            if gold_domain
            else 0
        )
        support = 0
        title_support = 0
        if terms:
            clause = " OR ".join(
                "(lower(coalesce(title,'')) LIKE ? OR lower(coalesce(abstract,'')) LIKE ? OR lower(coalesce(keywords,'')) LIKE ?)"
                for _ in terms
            )
            params = []
            for term in terms:
                pattern = f"%{term.lower()}%"
                params.extend([pattern, pattern, pattern])
            support = conn.execute(
                f"SELECT count(*) FROM papers WHERE {clause}", params
            ).fetchone()[0]
            title_clause = " OR ".join("lower(coalesce(title,'')) LIKE ?" for _ in terms)
            title_params = [f"%{term.lower()}%" for term in terms]
            title_support = conn.execute(
                f"SELECT count(*) FROM papers WHERE {title_clause}", title_params
            ).fetchone()[0]
        out.append(
            {
                "case_id": case["case_id"],
                "source": case.get("source"),
                "terms": terms,
                "available_support": support,
                "domain_l1": gold_domain,
                "domain_l2": labels.get(gold_id, {}).get("domain_l2"),
                "domain_available": domain_available,
                "domain_ceiling@10": round(min(1.0, domain_available / 10.0), 3) if gold_domain else 0.0,
                "title_support": title_support,
                "title_ceiling@10": round(min(1.0, title_support / 10.0), 3),
                "coverage_ceiling@10": round(min(1.0, support / 10.0), 3),
            }
        )
    return out

def result_hubness(path: Path | None) -> dict:
    if not path or not path.exists():
        return {"available": False}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    paper_queries: dict[str, set[str]] = defaultdict(set)
    per_query = []
    seen: set[str] = set()
    for row in rows:
        ids = list(row.get("top10_paper_ids") or [])
        for pid in ids:
            paper_queries[pid].add(row["case_id"])
        new = [pid for pid in ids if pid not in seen]
        observed = len(set(ids))
        per_query.append(
            {
                "case_id": row["case_id"],
                "distinct_papers@10": observed,
                "new_papers": len(new),
                "new_paper_rate": round(len(new) / observed, 3) if observed else 0,
            }
        )
        seen.update(ids)
    unique = len(paper_queries)
    hub = sum(1 for queries in paper_queries.values() if len(queries) >= 2)
    return {
        "available": True,
        "queries": len(rows),
        "unique_papers": unique,
        "hub_papers": hub,
        "hub_paper_rate": round(hub / unique, 3) if unique else 0,
        "top_hub_papers": sorted(
            ((pid, len(qs)) for pid, qs in paper_queries.items()),
            key=lambda item: -item[1],
        )[:10],
        "per_query": per_query,
        "mean_distinct_papers@10": round(
            sum(item["distinct_papers@10"] for item in per_query) / len(per_query), 3
        ) if per_query else 0,
        "mean_new_paper_rate": round(
            sum(item["new_paper_rate"] for item in per_query) / len(per_query), 3
        ) if per_query else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--cases", default=str(ROOT / "eval" / "plugins" / "retriever_queries.json"))
    parser.add_argument("--audit-json", default=str(ROOT / "eval" / "results" / "hybrid_bias_audit.json"))
    parser.add_argument("--labels", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cases = load_cases(Path(args.cases), 5)
    labels = load_labels(Path(args.labels) if args.labels else None)
    try:
        corpus = corpus_stats(conn, labels)
        support = query_support(conn, cases, labels)
    finally:
        conn.close()

    report = {
        "domain_labels": "present" if labels else "missing",
        "corpus": corpus,
        "query_support": support,
        "hubness": result_hubness(Path(args.audit_json) if args.audit_json else None),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({
        "domain_labels": report["domain_labels"],
        "papers": corpus["papers"],
        "journals": corpus["journals"],
        "journal_gini": corpus["journal_gini"],
        "singleton_journals": corpus["singleton_journals"],
        "top_journal_share": corpus["top_journal_share"],
        "mean_available_support": round(
            sum(item["available_support"] for item in support) / len(support), 3
        ) if support else 0,
        "mean_domain_available": round(
            sum(item["domain_available"] for item in support) / len(support), 3
        ) if support else 0,
        "mean_domain_ceiling": round(
            sum(item["domain_ceiling@10"] for item in support) / len(support), 3
        ) if support else 0,
        "mean_title_support": round(
            sum(item.get("title_support", 0) for item in support) / len(support), 3
        ) if support else 0,
        "mean_coverage_ceiling": round(
            sum(item["coverage_ceiling@10"] for item in support) / len(support), 3
        ) if support else 0,
        "hubness": {
            key: report["hubness"].get(key)
            for key in ("available", "hub_paper_rate", "mean_distinct_papers@10", "mean_new_paper_rate")
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
