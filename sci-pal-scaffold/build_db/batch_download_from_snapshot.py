"""
Batch download papers from local OpenAlex snapshot.

V20.0 — local snapshot → OpenAlex API → Unpaywall → download:
  1. Read local parquet files, filter for biology/medicine papers by topics
  2. Collect work_ids (sample N papers)
  3. OpenAlex API: batch look up DOI + journal + OA status (free for single lookups)
  4. Unpaywall: get PDF direct link
  5. Download PDF to documents/

Usage:
  python -m build_db.batch_download_from_snapshot
  python -m build_db.batch_download_from_snapshot --sample 200 --target-cell 10 --target-nature 10 --target-science 10
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import pyarrow.parquet as pq
import requests

# ── Config ──────────────────────────────────────────────────────────────────

EMAIL = "chenwei-ucas@outlook.com"
SNAPSHOT_DIR = Path("data/openalex_data/light_OpenAlex_works")
OUTPUT_DIR = Path("documents")
CACHE_FILE = Path("data/snapshot_work_ids_cache.json")
UNPAYWALL_DELAY = 0.2  # seconds between Unpaywall calls
OPENALEX_DELAY = 0.1   # seconds between OpenAlex API calls

# Biology/medicine domain IDs to filter
BIOLOGY_DOMAIN_IDS = {"1"}  # Life Sciences
BIOLOGY_FIELD_IDS = {"27", "13", "17", "23", "24", "26", "28"}  # Medicine, Immunology, etc.

# Target journal name keywords (case-insensitive substring match)
TARGET_JOURNALS = {
    "Cell": ["cell", "cell reports", "molecular cell", "neuron", "immunity",
             "cancer cell", "structure", "chem biol", "patterns", "device"],
    "Nature": ["nature", "nature cell biology", "nature medicine",
               "nature immunology", "nature biotechnology", "nature genetics",
               "nature methods", "nature neuroscience", "nature communications",
               "nature microbiology", "nature cancer", "nature aging"],
    "Science": ["science", "science advances", "science immunology",
                "science translational medicine", "science signaling",
                "science robotics", "science advances"],
}


# ── Step 1: Local parquet filter ───────────────────────────────────────────

def parse_topics(topics_str: str) -> list[dict]:
    """Parse topics JSON string, return list of topic dicts."""
    try:
        return json.loads(topics_str)
    except (json.JSONDecodeError, TypeError):
        return []


def is_biology_paper(topics_str: str) -> bool:
    """Check if paper belongs to biology/medicine domain."""
    topics = parse_topics(topics_str)
    for t in topics:
        subfield = t.get("subfield", {})
        field = t.get("field", {})
        domain = t.get("domain", {})
        domain_id = str(domain.get("id", "")).split("/")[-1]
        field_id = str(field.get("id", "")).split("/")[-1]
        if domain_id in BIOLOGY_DOMAIN_IDS:
            return True
        if field_id in BIOLOGY_FIELD_IDS:
            return True
    return False


def collect_work_ids(sample_size: int = 500) -> list[str]:
    """Scan local parquet files, collect biology work_ids."""
    if CACHE_FILE.exists():
        print(f"  Loading cached work_ids from {CACHE_FILE}")
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        if len(cached) >= sample_size:
            print(f"  Found {len(cached)} cached IDs, using first {sample_size}")
            return cached[:sample_size]
        return cached

    parquet_files = sorted(SNAPSHOT_DIR.glob("*.parquet"))
    print(f"  Scanning {len(parquet_files)} parquet files...")

    work_ids = []
    for pf in parquet_files:
        if len(work_ids) >= sample_size * 3:  # collect extra for filtering
            break
        print(f"    Reading {pf.name}...", end=" ", flush=True)
        table = pq.read_table(pf, columns=["work_id", "topics"])
        topics_col = table.column("topics").to_pylist()
        ids_col = table.column("work_id").to_pylist()

        count = 0
        for wid, topics_str in zip(ids_col, topics_col):
            if is_biology_paper(topics_str):
                work_ids.append(wid)
                count += 1
        print(f"{count} biology papers")

    # Save cache
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(work_ids, f)
    print(f"  Total biology work_ids: {len(work_ids)} (cached to {CACHE_FILE})")
    return work_ids


# ── Step 2: OpenAlex API lookup ────────────────────────────────────────────

def lookup_work(work_id_url: str) -> dict | None:
    """Look up a single work on OpenAlex, return DOI + journal + OA info."""
    # work_id_url is like https://openalex.org/W2353297661
    work_id = work_id_url.split("/")[-1]
    url = f"https://api.openalex.org/works/{work_id}"
    params = {"mailto": EMAIL}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            print("    Rate limited, waiting 5s...")
            time.sleep(5)
            r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as e:
        print(f"    Error: {e}")
        return None

    doi_raw = data.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "")
    title = data.get("title") or ""
    oa = data.get("open_access") or {}
    is_oa = oa.get("is_oa", False)
    oa_status = oa.get("oa_status", "") or ""

    # Get journal/source name
    primary_loc = data.get("primary_location") or {}
    source = primary_loc.get("source") or {}
    journal_name = source.get("display_name") or ""
    issn_l = source.get("issn_l") or ""

    return {
        "work_id": work_id,
        "doi": doi,
        "title": title,
        "journal": journal_name,
        "issn_l": issn_l,
        "is_oa": is_oa,
        "oa_status": oa_status,
    }


def match_journal(journal_name: str) -> str | None:
    """Match journal name to target category. Returns category or None."""
    jl = journal_name.lower()
    for category, keywords in TARGET_JOURNALS.items():
        for kw in keywords:
            if kw in jl:
                return category
    return None


# ── Step 3: Unpaywall download ─────────────────────────────────────────────

def get_pdf_url(doi: str) -> str | None:
    """Get PDF URL from Unpaywall."""
    url = f"https://api.unpaywall.org/v2/{doi}"
    try:
        r = requests.get(url, params={"email": EMAIL}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        best = data.get("best_oa_location") or {}
        return best.get("url_for_pdf") or best.get("url")
    except Exception:
        return None


def download_pdf(pdf_url: str, doi: str) -> Path | None:
    """Download PDF to documents/."""
    safe_doi = doi.replace("/", "_").replace(":", "-")
    filename = f"paper_{safe_doi}.pdf"
    filepath = OUTPUT_DIR / filename
    if filepath.exists() and filepath.stat().st_size > 10000:
        print(f"    Already exists: {filename}")
        return filepath

    try:
        r = requests.get(pdf_url, timeout=60, stream=True,
                         headers={"User-Agent": "SciPal/1.0 (mailto:chenwei-ucas@outlook.com)"})
        if r.status_code == 200 and "pdf" in r.headers.get("Content-Type", "").lower():
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_kb = filepath.stat().st_size / 1024
            print(f"    ✅ {filename} ({size_kb:.0f} KB)")
            return filepath
        else:
            print(f"    ❌ HTTP {r.status_code} (not PDF)")
    except Exception as e:
        print(f"    ❌ {e}")
    return None


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch download from OpenAlex snapshot")
    parser.add_argument("--sample", type=int, default=500, help="Number of work_ids to look up")
    parser.add_argument("--per-journal", type=int, default=5, help="Papers per journal category")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("📥 Batch Download from Local OpenAlex Snapshot")
    print("=" * 70)
    print(f"   Sample size: {args.sample}")
    print(f"   Per journal category: {args.per_journal}")

    # Step 1: collect work_ids
    print("\n🔍 Step 1: Scanning local parquet files for biology papers...")
    work_ids = collect_work_ids(args.sample)

    # Step 2: look up on OpenAlex
    print(f"\n🌐 Step 2: Looking up {min(len(work_ids), args.sample)} papers on OpenAlex...")
    results = []
    counts = {"Cell": 0, "Nature": 0, "Science": 0}

    for i, wid_url in enumerate(work_ids[:args.sample]):
        # Stop if we have enough from each category
        if all(c >= args.per_journal for c in counts.values()):
            print(f"\n  ✅ Enough papers from all categories, stopping at {i+1}")
            break

        work = lookup_work(wid_url)
        time.sleep(OPENALEX_DELAY)

        if not work or not work["is_oa"] or not work["doi"]:
            continue
        category = match_journal(work["journal"])
        if not category:
            continue
        if counts[category] >= args.per_journal:
            continue

        counts[category] += 1
        print(f"  [{i+1}/{args.sample}] {category}: {work['journal']} [{work['doi']}]")
        results.append(work)

    print(f"\n📊 Found {len(results)} OA papers from target journals:")
    for cat, count in counts.items():
        print(f"   {cat}: {count}")

    # Step 3: download via Unpaywall
    print(f"\n📄 Step 3: Downloading {len(results)} PDFs via Unpaywall...")
    downloaded = 0
    for work in results:
        doi = work["doi"]
        print(f"  → {work['journal']} [{doi}]")
        pdf_url = get_pdf_url(doi)
        time.sleep(UNPAYWALL_DELAY)
        if not pdf_url:
            print("    (no OA PDF found)")
            continue
        path = download_pdf(pdf_url, doi)
        if path:
            downloaded += 1

    print("\n" + "=" * 70)
    print(f"✅ Done: {downloaded}/{len(results)} PDFs in {OUTPUT_DIR}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
