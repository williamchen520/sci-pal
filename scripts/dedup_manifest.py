#!/usr/bin/env python3
"""Filter a download manifest against existing papers and itself."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db.pg_pool import pg_connection


def _doi(value: str | None) -> str:
    text = (value or "").strip().lower()
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", text)


def _title(value: str | None) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pmcid(row: dict) -> str:
    return str(row.get("pmcid") or "").upper().strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="F:/scipal_data/scale_10k_manifest.jsonl")
    parser.add_argument("--out", default="F:/scipal_data/scale_10k_dedup.jsonl")
    parser.add_argument("--report", default="F:/scipal_data/scale_10k_dedup_report.json")
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for line in Path(args.manifest).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pg = pg_connection()
    try:
        existing = pg.execute("SELECT paper_id, filename, doi, title FROM papers").fetchall()
    finally:
        pg.close()
    existing_pmcid, existing_doi, existing_title = set(), set(), set()
    for row in existing:
        pid = str(row["paper_id"] or "")
        fname = str(row["filename"] or "")
        if pid.startswith("paper_PMC"):
            existing_pmcid.add(pid.removeprefix("paper_").upper())
        if fname.upper().startswith("PMC"):
            existing_pmcid.add(fname.upper().removesuffix(".XML"))
        if _doi(row["doi"]):
            existing_doi.add(_doi(row["doi"]))
        if _title(row["title"]):
            existing_title.add(_title(row["title"]))

    stats = {"total": len(rows), "kept": 0, "existing": 0, "within": 0, "missing": 0}
    kept_pmcid, kept_doi, kept_title = set(), set(), set()
    out = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        pmcid, doi, title = _pmcid(row), _doi(row.get("doi")), _title(row.get("title"))
        reason = ""
        if pmcid and pmcid in existing_pmcid:
            reason = "existing_pmcid"
        elif doi and doi in existing_doi:
            reason = "existing_doi"
        elif title and title in existing_title:
            reason = "existing_title"
        elif pmcid and pmcid in kept_pmcid:
            reason = "within_pmcid"
        elif doi and doi in kept_doi:
            reason = "within_doi"
        elif title and title in kept_title:
            reason = "within_title"
        if reason.startswith("existing"):
            stats["existing"] += 1
        elif reason.startswith("within"):
            stats["within"] += 1
        if reason:
            row = {**row, "dedup_status": "duplicate", "dedup_reason": reason}
            out.append(row)
            continue
        item = {**row, "_pmcid": pmcid, "_doi": doi, "_title": title, "dedup_status": "kept"}
        out.append(item)
        if pmcid:
            kept_pmcid.add(pmcid)
        if doi:
            kept_doi.add(doi)
        if title:
            kept_title.add(title)
        stats["kept"] += 1
    for item in out:
        item.pop("_pmcid", None)
        item.pop("_doi", None)
        item.pop("_title", None)
    Path(args.out).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in out),
        encoding="utf-8",
    )
    Path(args.report).write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
