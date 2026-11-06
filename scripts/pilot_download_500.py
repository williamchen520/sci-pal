#!/usr/bin/env python3
"""Pilot downloader: 5-year monthly stratified Europe PMC OA XML."""

from __future__ import annotations

import argparse
import calendar
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.europe_pmc import EuropePMCClient


def _months(start: date, count: int = 60):
    y, m = start.year, start.month
    for _ in range(count):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _query(year: int, month: int) -> str:
    last = calendar.monthrange(year, month)[1]
    return (
        "OPEN_ACCESS:Y AND SRC:PMC AND HAS_FT:Y AND LANG:eng "
        f"AND FIRST_PDATE:[{year}-{month:02d}-01 TO {year}-{month:02d}-{last:02d}]"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=500)
    parser.add_argument("--per-month", type=int, default=12)
    parser.add_argument("--months", type=int, default=60)
    parser.add_argument("--start", default="2021-11")
    parser.add_argument("--out-dir", default="F:/scipal_data/documents_xml")
    parser.add_argument("--manifest", default="F:/scipal_data/pilot_500_manifest.jsonl")
    parser.add_argument("--seed", type=int, default=20261106)
    args = parser.parse_args()
    random.seed(args.seed)
    start_year, start_month = map(int, args.start.split("-"))
    client = EuropePMCClient(timeout=30)
    pool = []
    for index, (year, month) in enumerate(_months(date(start_year, start_month, 1), args.months)):
        try:
            rows = client.search_all(_query(year, month), max_items=200, page_size=100)
        except Exception as exc:  # noqa: BLE001
            print(f"{year}-{month:02d} search failed: {exc}", flush=True)
            continue
        candidates = [r for r in rows if r.get("pmcid")]
        take = min(args.per_month, len(candidates))
        picked = random.sample(candidates, take) if take else []
        pool.extend(picked)
        print(f"{year}-{month:02d} rows={len(rows)} picked={len(picked)}", flush=True)
        time.sleep(0.4)
    random.shuffle(pool)
    selected = pool[: args.target]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    ok = failed = skipped = 0
    with manifest.open("w", encoding="utf-8") as fh:
        for row in selected:
            pmcid = str(row["pmcid"]).upper()
            target = out_dir / f"{pmcid}.xml"
            item = {
                "pmcid": pmcid,
                "doi": row.get("doi"),
                "title": row.get("title"),
                "year": row.get("pubYear"),
                "journal": row.get("journalTitle"),
            }
            if target.exists():
                skipped += 1
                item["status"] = "exists"
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                continue
            try:
                xml = client.fetch_fulltext_xml(pmcid)
                if not xml:
                    failed += 1
                    item["status"] = "no_xml"
                else:
                    target.write_text(xml, encoding="utf-8")
                    ok += 1
                    item["status"] = "ok"
            except Exception as exc:  # noqa: BLE001
                failed += 1
                item["status"] = f"error:{str(exc)[:120]}"
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            time.sleep(0.25)
    print({"selected": len(selected), "ok": ok, "skipped": skipped, "failed": failed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
