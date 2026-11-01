#!/usr/bin/env python3
"""Export review-priority rows from the OpenAlex validation CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--confidence", default="low")
    parser.add_argument("--match", default="")
    parser.add_argument("--markdown", default="")
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    wanted_match = {item.strip().lower() for item in args.match.split(",") if item.strip()}
    selected = [
        row
        for row in rows
        if (row.get("ai_prelabel_confidence") or "").strip().lower() == args.confidence.lower()
        and (not wanted_match or (row.get("ai_prelabel_topic_match") or "").strip().lower() in wanted_match)
    ]
    selected.sort(key=lambda row: row.get("sample_id", ""))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if selected:
        with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(selected[0].keys()))
            writer.writeheader()
            writer.writerows(selected)
    else:
        out_path.write_text("", encoding="utf-8")

    if args.markdown:
        lines = [
            "# OpenAlex 低置信度校验清单",
            "",
            f"> Filter: confidence={args.confidence}, match={args.match or 'any'}  ",
            f"> Rows: {len(selected)}",
            "",
            "| sample | topic | title | match | OpenAlex | DOI |",
            "|---|---|---|---|---|---|",
        ]
        for row in selected:
            title = (row.get("title") or "").replace("|", " ")[:80]
            topic = (row.get("openalex_topic") or "").replace("|", " ")[:60]
            oa = row.get("openalex_url") or ""
            doi = f"https://doi.org/{row.get('doi','')}" if row.get("doi") else ""
            lines.append(
                f"| {row.get('sample_id','')} | {topic} | {title} | "
                f"{row.get('ai_prelabel_topic_match','')} | {oa} | {doi} |"
            )
        Path(args.markdown).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"rows": len(selected), "out": str(out_path), "markdown": args.markdown}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
