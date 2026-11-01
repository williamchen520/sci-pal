#!/usr/bin/env python3
"""AI-assisted prefill for the OpenAlex 100-paper validation set.

This does NOT replace human review. It writes `ai_prelabel_*` columns with
traceable evidence: OpenAlex work/topic, DOI, and Europe PMC MeSH when available.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = {
    "and", "or", "the", "of", "in", "on", "for", "to", "with", "a", "an",
    "by", "from", "as", "at", "is", "are", "be", "study", "research",
    "treatment", "patients", "disease", "diseases", "using", "based",
}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return {tok for tok in TOKEN_RE.findall((text or "").lower()) if tok not in STOP and len(tok) > 2}


def fetch_europepmc_batch(dois: list[str]) -> dict[str, dict]:
    query = urllib.parse.quote(" OR ".join(f'DOI:"{doi}"' for doi in dois))
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={query}&resultType=core&format=json&pageSize=100"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "SciPal/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {doi: {"ok": False, "error": str(exc), "mesh": [], "pmid": "", "url": ""} for doi in dois}
    results = (payload.get("resultList") or {}).get("result") or []
    found = {}
    for item in results:
        doi = (item.get("doi") or "").strip()
        mesh_block = (item.get("meshHeadingList") or {}).get("meshHeading") or []
        mesh = [entry.get("descriptorName") for entry in mesh_block if entry.get("descriptorName")]
        pmid = item.get("pmid") or ""
        found[doi] = {
            "ok": True,
            "mesh": mesh,
            "pmid": pmid,
            "url": f"https://europepmc.org/article/MED/{pmid}" if pmid else "",
        }
    return {
        doi: found.get(doi, {"ok": True, "mesh": [], "pmid": "", "url": ""})
        for doi in dois
    }

def prelabel(row: dict, epmc: dict) -> tuple[str, str, str, str]:
    topic = row.get("openalex_topic") or ""
    title_abs = f"{row.get('title','')} {row.get('abstract_snippet','')}"
    topic_tokens = tokens(topic)
    text_tokens = tokens(title_abs)
    overlap = topic_tokens & text_tokens

    mesh = epmc.get("mesh") or []
    mesh_text = " ".join(mesh)
    mesh_tokens = tokens(mesh_text)
    mesh_overlap = topic_tokens & mesh_tokens

    auto = (row.get("auto_domain_l1") or "").strip().lower()
    auto_keywords = {
        "alzheimers": {"dementia", "alzheimer", "cognitive", "neuro"},
        "hcc_io": {"hepatocellular", "liver", "hcc", "carcinoma"},
        "oncology_other": {"cancer", "tumor", "oncology", "carcinoma", "immunotherapy"},
        "microbiology": {"microbiology", "microbial", "virus", "viral", "bacteria", "infection"},
        "endocrinology": {"diabetes", "endocrine", "hormone", "metabolic"},
    }.get(auto, set())
    auto_support = bool(
        (auto_keywords & topic_tokens)
        or (auto_keywords & tokens(row.get("title", "")))
    )

    if mesh_overlap:
        match = "yes"
        confidence = "high"
        basis = "Europe PMC MeSH overlap: " + ", ".join(sorted(mesh_overlap)[:5])
    elif auto_support:
        match = "yes"
        confidence = "medium"
        basis = f"auto label {auto} supports topic"
    elif len(overlap) >= 2:
        match = "yes"
        confidence = "medium"
        basis = "title/abstract overlap: " + ", ".join(sorted(overlap)[:5])
    elif len(overlap) == 1 or mesh:
        match = "partial"
        confidence = "low"
        basis = (
            "single title/abstract overlap: " + next(iter(overlap))
            if overlap
            else "MeSH exists but no topic token overlap"
        )
    else:
        match = "no"
        confidence = "low"
        basis = "no lexical/MeSH overlap"

    domain = row.get("openalex_domain") or "unknown"
    evidence_parts = [
        f"OpenAlex={row.get('openalex_url') or row.get('openalex_id') or ''}",
        f"topic={topic}",
        f"field={row.get('openalex_field') or ''}",
        f"DOI=https://doi.org/{row.get('doi') or ''}",
        f"auto={auto or '(none)'}",
    ]
    if mesh:
        evidence_parts.append("MeSH=" + "; ".join(mesh[:8]))
    if epmc.get("url"):
        evidence_parts.append("EuropePMC=" + epmc["url"])
    evidence_parts.append("basis=" + basis)
    return domain, match, confidence, " | ".join(evidence_parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "eval" / "validation" / "openalex_100.csv"))
    parser.add_argument("--out", default=str(ROOT / "eval" / "validation" / "openalex_100_prefilled.csv"))
    parser.add_argument("--cache", default=str(ROOT / "eval" / "validation" / "europepmc_cache.json"))
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    cache_path = Path(args.cache)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    missing = []
    for row in rows:
        doi = (row.get("doi") or "").strip()
        if doi and doi not in cache:
            missing.append(doi)
    for start in range(0, len(missing), 20):
        batch = missing[start:start + 20]
        cache.update(fetch_europepmc_batch(batch))
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"EuropePMC batch {min(start + 20, len(missing))}/{len(missing)}", flush=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    out_rows = []
    matches = Counter()
    confidences = Counter()
    for row in rows:
        epmc = cache.get((row.get("doi") or "").strip(), {"ok": True, "mesh": [], "pmid": "", "url": ""})
        domain, match, confidence, evidence = prelabel(row, epmc)
        row = dict(row)
        row["ai_prelabel_domain"] = domain
        row["ai_prelabel_topic_match"] = match
        row["ai_prelabel_confidence"] = confidence
        row["ai_evidence"] = evidence
        row["ai_notes"] = "AI prelabel only; human review required"
        out_rows.append(row)
        matches[match] += 1
        confidences[confidence] += 1

    with Path(args.out).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    summary = {
        "rows": len(out_rows),
        "topic_match": dict(matches),
        "confidence": dict(confidences),
        "europepmc_hits": sum(1 for item in cache.values() if item.get("mesh")),
        "out": str(args.out),
    }
    Path(args.out).with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
