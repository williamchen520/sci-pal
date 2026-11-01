#!/usr/bin/env python3
"""Probe OpenAlex DOI coverage for the local paper corpus."""

from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.openalex.org/works"


def normalize_doi(value: str) -> str:
    text = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return text.strip()


def load_dois(db: Path, limit: int = 0, sample_seed: int | None = None) -> list[tuple[str, str]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT paper_id, doi FROM papers WHERE doi IS NOT NULL AND trim(doi) != '' ORDER BY paper_id"
        ).fetchall()
    finally:
        conn.close()
    out = [(paper_id, normalize_doi(doi)) for paper_id, doi in rows if normalize_doi(doi)]
    if sample_seed is not None:
        random.Random(sample_seed).shuffle(out)
    return out[:limit] if limit else out


def fetch_batch(dois: list[str], mailto: str, api_key: str, timeout: int = 60) -> tuple[list[dict], dict]:
    query = "|".join(urllib.parse.quote(doi, safe="") for doi in dois)
    params = {
        "filter": f"doi:{query}",
        "per-page": str(min(50, len(dois))),
        "select": "id,doi,title,primary_topic,topics",
    }
    if mailto:
        params["mailto"] = mailto
    if api_key:
        params["api_key"] = api_key
    # Do not urlencode the whole filter again: DOI slashes are already %2F.
    url = API + "?" + "&".join(f"{key}={value}" for key, value in params.items())
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"SciPal/0.1 (mailto:{mailto or 'unknown'})"},
    )
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload.get("results") or [], payload.get("meta") or {}
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"OpenAlex batch failed: {last_error}")


def topic_row(work: dict) -> dict:
    primary = work.get("primary_topic") or {}
    domain = primary.get("domain") or {}
    field = primary.get("field") or {}
    subfield = primary.get("subfield") or {}
    return {
        "openalex_id": work.get("id"),
        "doi": normalize_doi(work.get("doi") or ""),
        "title": work.get("title"),
        "topic_id": primary.get("id"),
        "topic_name": primary.get("display_name"),
        "domain_id": domain.get("id"),
        "domain_name": domain.get("display_name"),
        "field_id": field.get("id"),
        "field_name": field.get("display_name"),
        "subfield_id": subfield.get("id"),
        "subfield_name": subfield.get("display_name"),
        "topics": [
            {
                "id": item.get("id"),
                "name": item.get("display_name"),
                "score": item.get("score"),
            }
            for item in (work.get("topics") or [])
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sample-seed", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--mailto", default=os.environ.get("OPENALEX_MAILTO", "scipal@example.org"))
    parser.add_argument("--api-key", default=os.environ.get("OPENALEX_API_KEY", ""))
    parser.add_argument("--out", default=str(ROOT / "eval" / "results" / "openalex_coverage.json"))
    args = parser.parse_args()

    papers = load_dois(Path(args.db), args.limit, args.sample_seed)
    by_doi = {doi: paper_id for paper_id, doi in papers}
    fetched: dict[str, dict] = {}
    errors = []
    batch_size = max(1, min(args.batch_size, 50))
    for start in range(0, len(papers), batch_size):
        batch = papers[start : start + batch_size]
        try:
            works, meta = fetch_batch([doi for _, doi in batch], args.mailto, args.api_key)
        except Exception as exc:  # noqa: BLE001
            errors.append({"start": start, "error": str(exc)})
            continue
        for work in works:
            row = topic_row(work)
            doi = row["doi"]
            if doi in by_doi:
                fetched[doi] = row
        print(f"batched {start + len(batch)}/{len(papers)} fetched={len(fetched)} errors={len(errors)}", flush=True)
        if not args.api_key:
            time.sleep(0.15)

    missing = [doi for _, doi in papers if doi not in fetched]
    domains = Counter(row.get("domain_name") or "(unknown)" for row in fetched.values())
    topics = Counter(row.get("topic_name") or "(unknown)" for row in fetched.values())
    report = {
        "papers": len(papers),
        "fetched": len(fetched),
        "missing": len(missing),
        "coverage_rate": round(len(fetched) / len(papers), 4) if papers else 0,
        "errors": errors,
        "top_domains": domains.most_common(20),
        "top_topics": topics.most_common(20),
        "missing_sample": missing[:50],
        "rows": {
            by_doi[doi]: row for doi, row in fetched.items() if doi in by_doi
        },
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("papers", "fetched", "missing", "coverage_rate", "errors")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
