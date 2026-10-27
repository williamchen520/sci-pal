"""Metadata / OA discovery clients.

These sources do not provide full text; they enrich metadata and point to OA
PDFs which then go through the PDF pipeline.

* Crossref            — canonical metadata, reference lists
* OpenAlex            — metadata, citation graph
* Semantic Scholar    — metadata, references, TLDR
* Unpaywall           — OA locations (requires email)
* CORE                — aggregated full-text links (API key optional)
* DOAJ                — open-access journal metadata
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

UA = {"User-Agent": "SciPal/1.0 (mailto:scipal@example.org)"}


def _get(url: str, params: Dict[str, Any] | None = None, timeout: int = 30) -> Dict[str, Any]:
    response = requests.get(url, params=params, headers=UA, timeout=timeout)
    response.raise_for_status()
    return response.json()


def crossref_work(doi: str) -> Dict[str, Any]:
    data = _get(f"https://api.crossref.org/works/{doi}")["message"]
    return {
        "source": "crossref",
        "doi": data.get("DOI"),
        "title": (data.get("title") or [""])[0],
        "journal": (data.get("container-title") or [""])[0],
        "year": (data.get("issued", {}).get("date-parts") or [[None]])[0][0],
        "authors": [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in data.get("author", [])
        ],
        "references": [
            {"doi": r.get("DOI"), "title": (r.get("article-title") or "")}
            for r in data.get("reference", [])
        ],
    }


def crossref_search(title: str, rows: int = 1) -> Dict[str, Any]:
    """Find the best Crossref candidate by bibliographic title."""
    data = _get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": title, "rows": rows},
    )
    items = (data.get("message") or {}).get("items") or []
    if not items:
        return {}
    item = items[0]
    return {
        "source": "crossref_search",
        "doi": item.get("DOI"),
        "title": (item.get("title") or [""])[0],
        "journal": (item.get("container-title") or [""])[0],
        "year": (item.get("issued", {}).get("date-parts") or [[None]])[0][0],
        "authors": [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
        ],
    }


def openalex_search(title: str, per_page: int = 1) -> Dict[str, Any]:
    """Find the best OpenAlex candidate by title (used when Crossref misses)."""
    data = _get(
        "https://api.openalex.org/works",
        params={"search": title, "per-page": per_page},
    )
    items = data.get("results") or []
    if not items:
        return {}
    item = items[0]
    venue = (item.get("primary_location") or {}).get("source") or {}
    authors = [
        (authorship.get("author") or {}).get("display_name", "")
        for authorship in item.get("authorships", [])
    ]
    return {
        "source": "openalex_search",
        "doi": (item.get("doi") or "").replace("https://doi.org/", "") or None,
        "title": item.get("title"),
        "journal": venue.get("display_name"),
        "year": item.get("publication_year"),
        "authors": [a for a in authors if a],
    }


def openalex_work(doi: str) -> Dict[str, Any]:
    data = _get(f"https://api.openalex.org/works/https://doi.org/{doi}")
    return {
        "source": "openalex",
        "id": data.get("id"),
        "doi": data.get("doi"),
        "title": data.get("title"),
        "year": data.get("publication_year"),
        "cited_by_count": data.get("cited_by_count"),
        "referenced_works": data.get("referenced_works") or [],
    }


def semantic_scholar(doi: str, fields: str = "title,abstract,year,references.title,tldr") -> Dict[str, Any]:
    data = _get(
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
        params={"fields": fields},
    )
    return {
        "source": "semantic_scholar",
        "title": data.get("title"),
        "abstract": data.get("abstract"),
        "year": data.get("year"),
        "tldr": (data.get("tldr") or {}).get("text"),
        "references": data.get("references") or [],
    }


def unpaywall(doi: str, email: str) -> Dict[str, Any]:
    data = _get(f"https://api.unpaywall.org/v2/{doi}", params={"email": email})
    best = data.get("best_oa_location") or {}
    return {
        "source": "unpaywall",
        "is_oa": data.get("is_oa"),
        "oa_status": data.get("oa_status"),
        "pdf_url": best.get("url_for_pdf"),
        "landing_url": best.get("url"),
    }


def core_search(query: str, api_key: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    if not api_key:
        return []
    data = _get(
        "https://api.core.ac.uk/v3/search/works",
        params={"q": query, "limit": limit},
    )
    return [
        {
            "source": "core",
            "id": item.get("id"),
            "title": item.get("title"),
            "doi": item.get("doi"),
            "download_url": item.get("downloadUrl"),
            "year": item.get("yearPublished"),
        }
        for item in data.get("results", [])
    ]


def doaj_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    data = _get(
        "https://doaj.org/api/search/articles/" + requests.utils.quote(query),
        params={"pageSize": limit},
    )
    results = []
    for item in data.get("results", []):
        bib = item.get("bibjson", {})
        results.append(
            {
                "source": "doaj",
                "title": bib.get("title"),
                "doi": next(
                    (i.get("id") for i in bib.get("identifier", []) if i.get("type") == "doi"),
                    None,
                ),
                "year": bib.get("year"),
                "journal": (bib.get("journal") or {}).get("title"),
            }
        )
    return results


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--doi")
    parser.add_argument("--crossref", action="store_true")
    parser.add_argument("--openalex", action="store_true")
    parser.add_argument("--s2", action="store_true")
    parser.add_argument("--unpaywall", action="store_true")
    parser.add_argument("--email", default="scipal@example.org")
    args = parser.parse_args()
    if args.doi and args.crossref:
        print(json.dumps(crossref_work(args.doi), ensure_ascii=False))
    elif args.doi and args.openalex:
        print(json.dumps(openalex_work(args.doi), ensure_ascii=False))
    elif args.doi and args.s2:
        print(json.dumps(semantic_scholar(args.doi), ensure_ascii=False))
    elif args.doi and args.unpaywall:
        print(json.dumps(unpaywall(args.doi, args.email), ensure_ascii=False))
