"""Preprint ingest: arXiv / bioRxiv / medRxiv -> PDF -> parse pipeline.

Preprints have no JATS; they provide metadata (Atom/JSON) and a PDF. The PDF
goes through the normal three-engine pipeline and the preprint metadata is
patched onto the resulting paper row.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from services.search.preprint_sources import (
    download_pdf,
    fetch_biorxiv,
    search_arxiv,
)

DEFAULT_DOCS = Path(__file__).resolve().parent.parent.parent / "documents"
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def _patch_metadata(db_path: Path | str, paper_id: str, meta: Dict[str, Any]) -> None:
    authors = meta.get("authors")
    if isinstance(authors, list):
        authors = "; ".join(a for a in authors if a)
    fields = {
        "title": meta.get("title"),
        "authors": authors,
        "year": (meta.get("published") or meta.get("date") or "")[:4] or None,
        "doi": meta.get("doi"),
    }
    fields = {k: v for k, v in fields.items() if v}
    if not fields:
        return
    conn = sqlite3.connect(str(db_path))
    try:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE papers SET {assignments} WHERE paper_id = ?",
            [*fields.values(), paper_id],
        )
        conn.commit()
    finally:
        conn.close()


def ingest_pdf(
    pdf_url: str,
    filename: str,
    meta: Dict[str, Any],
    documents_dir: Path | str = DEFAULT_DOCS,
    db_path: Path | str = DEFAULT_DB,
    parse: bool = True,
) -> Dict[str, Any]:
    target = Path(documents_dir) / filename
    download_pdf(pdf_url, target)
    result: Dict[str, Any] = {"file": str(target), "parsed": False}
    if not parse:
        return result

    from build_db.parse_service import parse_and_store

    stats = parse_and_store(db_path, target, target.name)
    result.update({"parsed": True, **stats})
    _patch_metadata(db_path, stats.get("paper_id", ""), meta)
    return result


def ingest_arxiv(
    query: str,
    max_items: int = 1,
    documents_dir: Path | str = DEFAULT_DOCS,
    db_path: Path | str = DEFAULT_DB,
    parse: bool = True,
) -> List[Dict[str, Any]]:
    results = []
    for item in search_arxiv(query, max_results=max_items):
        if not item.get("pdf_url"):
            continue
        filename = f"arxiv_{item['id'].replace('/', '_')}.pdf"
        results.append(
            ingest_pdf(
                item["pdf_url"], filename, item,
                documents_dir=documents_dir, db_path=db_path, parse=parse,
            )
        )
    return results


def ingest_biorxiv(
    doi: str,
    server: str = "biorxiv",
    documents_dir: Path | str = DEFAULT_DOCS,
    db_path: Path | str = DEFAULT_DB,
    parse: bool = True,
) -> Dict[str, Any] | None:
    item = fetch_biorxiv(doi, server)
    if not item or not item.get("pdf_url"):
        return None
    filename = f"{server}_{doi.replace('/', '_')}.pdf"
    return ingest_pdf(
        item["pdf_url"], filename, item,
        documents_dir=documents_dir, db_path=db_path, parse=parse,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv")
    parser.add_argument("--biorxiv")
    parser.add_argument("--medrxiv")
    parser.add_argument("--max-items", type=int, default=1)
    parser.add_argument("--no-parse", action="store_true")
    args = parser.parse_args()

    if args.arxiv:
        out = ingest_arxiv(args.arxiv, args.max_items, parse=not args.no_parse)
    elif args.biorxiv:
        out = ingest_biorxiv(args.biorxiv, "biorxiv", parse=not args.no_parse)
    elif args.medrxiv:
        out = ingest_biorxiv(args.medrxiv, "medrxiv", parse=not args.no_parse)
    else:
        parser.error("需要 --arxiv / --biorxiv / --medrxiv")
    print(json.dumps(out, ensure_ascii=False))
