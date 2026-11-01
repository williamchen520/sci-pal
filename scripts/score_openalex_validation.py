#!/usr/bin/env python3
"""Score filled OpenAlex human-validation CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    total = len(rows)
    filled = [row for row in rows if (row.get("human_domain") or "").strip()]
    domain_ok = [
        row for row in filled
        if (row.get("human_domain") or "").strip() == (row.get("openalex_domain") or "").strip()
    ]
    topic = Counter(
        (row.get("human_topic_match") or "").strip().lower()
        for row in filled
        if (row.get("human_topic_match") or "").strip()
    )
    by_domain = {}
    for row in filled:
        domain = row.get("openalex_domain") or "(unknown)"
        bucket = by_domain.setdefault(domain, {"n": 0, "domain_ok": 0, "topic_yes": 0})
        bucket["n"] += 1
        if (row.get("human_domain") or "").strip() == domain:
            bucket["domain_ok"] += 1
        if (row.get("human_topic_match") or "").strip().lower() == "yes":
            bucket["topic_yes"] += 1
    report = {
        "rows": total,
        "filled": len(filled),
        "completed_rate": round(len(filled) / total, 4) if total else 0,
        "domain_agreement": round(len(domain_ok) / len(filled), 4) if filled else None,
        "topic_yes": topic.get("yes", 0),
        "topic_partial": topic.get("partial", 0),
        "topic_no": topic.get("no", 0),
        "topic_exact_rate": round(topic.get("yes", 0) / len(filled), 4) if filled else None,
        "topic_partial_rate": round(topic.get("partial", 0) / len(filled), 4) if filled else None,
        "topic_wrong_rate": round(topic.get("no", 0) / len(filled), 4) if filled else None,
        "by_domain": by_domain,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
