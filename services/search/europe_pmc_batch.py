"""Europe PMC batch fetch: search -> OA full-text XML -> structured import.

Differences from the PDF pipeline: Europe PMC returns JATS XML, so each item
goes through ``build_db.import_jats`` (sections/refs/figures/xref links), not
Docling/GROBID/MinerU.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from services.search.europe_pmc import DEFAULT_DB, DEFAULT_XML_DIR, EuropePMCClient


def select_open_access(results: List[Dict[str, Any]]) -> List[str]:
    """Keep results that have a PMCID and are (declared) open access."""
    pmcids = []
    for item in results:
        pmcid = item.get("pmcid")
        if not pmcid:
            continue
        if str(item.get("isOpenAccess", "")).upper() not in ("Y", "YES", "TRUE", "1"):
            continue
        pmcids.append(pmcid)
    return pmcids


def batch_import(
    pmcids: List[str],
    client: EuropePMCClient | None = None,
    xml_dir: Path | str = DEFAULT_XML_DIR,
    db_path: Path | str = DEFAULT_DB,
    limit: int = 0,
) -> Dict[str, Any]:
    client = client or EuropePMCClient()
    summary: Dict[str, Any] = {
        "requested": len(pmcids),
        "imported": 0,
        "no_fulltext": 0,
        "failed": 0,
        "sections": 0,
        "paragraphs": 0,
        "sentences": 0,
        "links": 0,
        "failures": [],
    }
    for pmcid in pmcids:
        if limit and summary["imported"] >= limit:
            break
        try:
            result = client.download_and_import(pmcid, xml_dir=xml_dir, db_path=db_path)
        except Exception as exc:  # noqa: BLE001
            summary["failed"] += 1
            summary["failures"].append({"pmcid": pmcid, "error": str(exc)[:160]})
            continue
        if result.get("status") == "no_fulltext":
            summary["no_fulltext"] += 1
            continue
        summary["imported"] += 1
        for key in ("sections", "paragraphs", "sentences", "links"):
            summary[key] += int(result.get(key, 0))
    return summary


def run_query(
    query: str,
    max_items: int = 20,
    client: EuropePMCClient | None = None,
    xml_dir: Path | str = DEFAULT_XML_DIR,
    db_path: Path | str = DEFAULT_DB,
    limit: int = 0,
) -> Dict[str, Any]:
    client = client or EuropePMCClient()
    results = client.search(query, page_size=max_items)
    pmcids = select_open_access(results)
    summary = batch_import(
        pmcids, client=client, xml_dir=xml_dir, db_path=db_path, limit=limit
    )
    summary["candidates"] = len(pmcids)
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query")
    parser.add_argument("--pmcids", nargs="*")
    parser.add_argument("--max-items", type=int, default=20)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--xml-dir", default=str(DEFAULT_XML_DIR))
    args = parser.parse_args()

    if args.pmcids:
        result = batch_import(
            args.pmcids, xml_dir=args.xml_dir, db_path=args.db, limit=args.limit
        )
    elif args.query:
        result = run_query(
            args.query,
            max_items=args.max_items,
            xml_dir=args.xml_dir,
            db_path=args.db,
            limit=args.limit,
        )
    else:
        parser.error("需要 --query 或 --pmcids")
    print(json.dumps(result, ensure_ascii=False))
