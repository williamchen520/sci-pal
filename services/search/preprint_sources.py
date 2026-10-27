"""Preprint sources: arXiv (Atom) + bioRxiv / medRxiv (JSON).

These sources do not provide JATS; they give metadata + PDF. Use them to feed
the PDF pipeline (docling + GROBID + MinerU), not the JATS importer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

import requests

ARXIV_API = "http://export.arxiv.org/api/query"
BIORXIV_API = "https://api.biorxiv.org/details"
ATOM = "{http://www.w3.org/2005/Atom}"


def _arxiv_entry(entry: ET.Element) -> Dict[str, Any]:
    pdf_url = ""
    for link in entry.findall(f"{ATOM}link"):
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            pdf_url = link.get("href", "")
            break
    return {
        "source": "arxiv",
        "id": (entry.findtext(f"{ATOM}id") or "").rsplit("/", 1)[-1],
        "title": " ".join((entry.findtext(f"{ATOM}title") or "").split()),
        "abstract": " ".join((entry.findtext(f"{ATOM}summary") or "").split()),
        "published": entry.findtext(f"{ATOM}published"),
        "pdf_url": pdf_url,
    }


def search_arxiv(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    response = requests.get(
        ARXIV_API,
        params={"search_query": query, "max_results": max_results},
        timeout=30,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    return [_arxiv_entry(entry) for entry in root.findall(f"{ATOM}entry")]


def fetch_biorxiv(doi: str, server: str = "biorxiv") -> Dict[str, Any] | None:
    response = requests.get(f"{BIORXIV_API}/{server}/{doi}", timeout=30)
    response.raise_for_status()
    collection = (response.json() or {}).get("collection") or []
    if not collection:
        return None
    item = collection[0]
    return {
        "source": server,
        "doi": item.get("doi"),
        "title": item.get("title"),
        "authors": item.get("authors"),
        "date": item.get("date"),
        "abstract": item.get("abstract"),
        "pdf_url": item.get("pdf") or f"https://www.{server}.org/content/{doi}v1.full.pdf",
    }


def download_pdf(url: str, target: Path | str, timeout: int = 120) -> Path:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--arxiv")
    parser.add_argument("--biorxiv")
    parser.add_argument("--medrxiv")
    args = parser.parse_args()
    if args.arxiv:
        for item in search_arxiv(args.arxiv):
            print(json.dumps(item, ensure_ascii=False))
    elif args.biorxiv:
        print(json.dumps(fetch_biorxiv(args.biorxiv, "biorxiv"), ensure_ascii=False))
    elif args.medrxiv:
        print(json.dumps(fetch_biorxiv(args.medrxiv, "medrxiv"), ensure_ascii=False))
