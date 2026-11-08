"""P3b: fetch a small CC BY PMC OA benchmark corpus (files only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SEARCH = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
    + urllib.parse.urlencode(
        {
            "query": 'OPEN_ACCESS:y AND LICENSE:"CC BY"',
            "format": "json",
            "pageSize": 60,
            "resultType": "core",
        }
    )
)
OUT = Path(r"F:/scipal_data/bench_pmc_oa")
MANIFEST = Path(r"D:/sciPal/eval/bench/p3b_manifest.json")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SciPal/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    data = json.loads(_get(SEARCH).decode("utf-8"))
    candidates = []
    for row in data.get("resultList", {}).get("result", []):
        pmcid = (row.get("pmcid") or "").upper()
        license_text = (row.get("license") or "").strip().lower()
        if not pmcid or "cc by" not in license_text:
            continue
        candidates.append(
            {
                "pmcid": pmcid,
                "doi": row.get("doi") or "",
                "title": row.get("title") or "",
                "license": row.get("license") or "",
                "first_publication_date": row.get("firstPublicationDate") or "",
            }
        )
    candidates = candidates[: args.limit]
    OUT.mkdir(parents=True, exist_ok=True)

    def fetch(item):
        payload = b""
        last = None
        urls = [
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/{item['pmcid']}/fullTextXML",
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={item['pmcid']}&retmode=xml",
        ]
        for url in urls:
            try:
                candidate = _get(url)
                if b"<article" in candidate[:8192]:
                    payload = candidate
                    break
                last = ValueError("not JATS")
            except Exception as exc:  # noqa: BLE001
                last = exc
        if not payload:
            raise last or ValueError("no JATS")
        if b"<article" not in payload[:8192]:
            raise ValueError("not JATS")
        path = OUT / f"{item['pmcid']}.xml"
        path.write_bytes(payload)
        item["path"] = str(path)
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["bytes"] = len(payload)
        return item

    ok, failed = [], []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, item): item for item in candidates}
        for future in as_completed(futures):
            item = futures[future]
            try:
                ok.append(future.result())
            except Exception as exc:  # noqa: BLE001
                failed.append({"pmcid": item["pmcid"], "error": str(exc)[:160]})

    ok.sort(key=lambda x: x["pmcid"])
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps({"source": "Europe PMC CC BY", "items": ok, "failed": failed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"downloaded={len(ok)} failed={len(failed)} out={OUT}")
    for item in ok[:5]:
        print(item["pmcid"], item["title"][:70])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
