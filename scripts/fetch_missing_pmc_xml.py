"""Download missing PMC JATS XML files referenced by public.papers.

Read-only against PostgreSQL. Writes files only, never rows.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db.pg_pool import pg_connection

PRIMARY = Path(r"F:/scipal_data/documents_xml")
SECONDARY = Path(r"D:/sciPal/documents_xml")
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
NCBI_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmcid}&retmode=xml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id, filename FROM papers "
            "WHERE lower(filename) LIKE '%.xml' ORDER BY paper_id"
        ).fetchall()
    finally:
        pg.close()

    targets = []
    for row in rows:
        name = row["filename"]
        if (PRIMARY / name).exists() or (SECONDARY / name).exists():
            continue
        match = re.search(r"(PMC\d+)", name, re.I)
        if match:
            targets.append((row["paper_id"], name, match.group(1).upper()))
    if args.limit:
        targets = targets[: args.limit]

    print(f"missing={len(targets)} primary={PRIMARY}")
    if not args.download:
        for item in targets[:20]:
            print("MISSING", item)
        return 0

    PRIMARY.mkdir(parents=True, exist_ok=True)

    def download_one(item):
        paper_id, name, pmcid = item
        url = URL.format(pmcid=pmcid)
        try:
            payload = b""
            last_error = None
            for candidate in (url, NCBI_URL.format(pmcid=pmcid)):
                try:
                    req = urllib.request.Request(candidate, headers={"User-Agent": "SciPal/1.0"})
                    with urllib.request.urlopen(req, timeout=45) as response:
                        payload = response.read()
                    if b"<article" in payload[:8192]:
                        break
                    last_error = ValueError("response is not a JATS article")
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            if b"<article" not in payload[:8192]:
                raise last_error or ValueError("no JATS article")
            tmp = PRIMARY / (name + ".part")
            tmp.write_bytes(payload)
            tmp.replace(PRIMARY / name)
            return True, item, ""
        except Exception as exc:  # noqa: BLE001
            return False, item, str(exc)[:200]

    ok = failed = 0
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(download_one, item) for item in targets]
        for i, future in enumerate(as_completed(futures), 1):
            success, item, error = future.result()
            if success:
                ok += 1
            else:
                failed += 1
                failures.append({"paper_id": item[0], "filename": item[1], "error": error})
                print(f"FAIL {item[2]} {error}")
            if i % 25 == 0:
                print(f"progress {i}/{len(targets)} ok={ok} failed={failed}")
            if args.sleep:
                time.sleep(max(0.0, args.sleep))

    report = {"targets": len(targets), "ok": ok, "failed": failed, "failures": failures}
    Path(r"G:/runs/missing_xml_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
