#!/usr/bin/env python3
"""Scale downloader: 5-year monthly stratified Europe PMC OA XML."""

from __future__ import annotations

import argparse
import calendar
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--per-month", type=int, default=200)
    parser.add_argument("--months", type=int, default=60)
    parser.add_argument("--start", default="2021-11")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out-dir", default="F:/scipal_data/documents_xml")
    parser.add_argument("--manifest", default="F:/scipal_data/scale_10k_manifest.jsonl")
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()
    random.seed(args.seed)
    start_year, start_month = map(int, args.start.split("-"))
    client = EuropePMCClient(timeout=30)
    pool = []
    for year, month in _months(date(start_year, start_month, 1), args.months):
        try:
            rows = client.search_all(_query(year, month), max_items=200, page_size=100)
        except Exception as exc:  # noqa: BLE001
            print(f"{year}-{month:02d} search failed: {exc}", flush=True)
            continue
        picked = random.sample([r for r in rows if r.get("pmcid")], min(args.per_month, len(rows)))
        pool.extend(picked)
        print(f"{year}-{month:02d} pool={len(pool)}", flush=True)
        time.sleep(0.3)
    random.shuffle(pool)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    state = {"ok": 0, "failed": 0, "skipped": 0}

    def fetch(row):
        pmcid = str(row["pmcid"]).upper()
        target = out_dir / f"{pmcid}.xml"
        item = {
            "pmcid": pmcid,
            "doi": row.get("doi"),
            "title": row.get("title"),
            "year": row.get("pubYear"),
            "journal": row.get("journalTitle"),
        }
        if target.exists() and target.stat().st_size > 0:
            item["status"] = "exists"
            return item
        try:
            xml = client.fetch_fulltext_xml(pmcid)
            if not xml:
                item["status"] = "no_xml"
            else:
                target.write_text(xml, encoding="utf-8")
                item["status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            item["status"] = f"error:{str(exc)[:120]}"
        return item

    with manifest.open("w", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.workers) as pool_ex:
        futures = [pool_ex.submit(fetch, row) for row in pool]
        done = 0
        for future in as_completed(futures):
            item = future.result()
            status = item["status"]
            with lock:
                if status in ("ok", "exists"):
                    state["ok"] += 1
                elif status == "no_xml":
                    state["failed"] += 1
                else:
                    state["failed"] += 1
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                fh.flush()
                done += 1
                if done % 200 == 0:
                    print({"done": done, **state}, flush=True)
            if state["ok"] >= args.target:
                break
        for future in futures:
            future.cancel()
    print({"target": args.target, **state}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
