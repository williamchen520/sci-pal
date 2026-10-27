"""Europe PMC client: search + full-text JATS XML fetch.

Europe PMC exposes REST endpoints without a key:

* ``/search?query=...&format=json``           — metadata / discovery
* ``/{PMCID}/fullTextXML``                    — JATS full text (OA subset)
* ``/{PMCID}/supplementaryFiles``             — optional

Full text is JATS, so it goes through ``build_db.import_jats`` — not the PDF
pipeline. Fetched XML is stored in ``documents_xml/`` and imported immediately
by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import requests

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
DEFAULT_XML_DIR = Path(__file__).resolve().parent.parent.parent / "documents_xml"
DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


class EuropePMCClient:
    def __init__(self, base_url: str = BASE, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(self, query: str, page_size: int = 25) -> List[Dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": page_size,
                "resultType": "core",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("resultList", {}).get("result", []) or []

    def fetch_fulltext_xml(self, pmcid: str) -> str | None:
        if not pmcid.upper().startswith("PMC"):
            pmcid = f"PMC{pmcid}"
        response = requests.get(
            f"{self.base_url}/{pmcid}/fullTextXML", timeout=self.timeout
        )
        if response.status_code != 200 or not response.text.strip():
            return None
        return response.text

    def download_and_import(
        self,
        pmcid: str,
        xml_dir: Path | str = DEFAULT_XML_DIR,
        db_path: Path | str = DEFAULT_DB,
    ) -> Dict[str, Any]:
        """Fetch full text, save as documents_xml/<PMCID>.xml, import to DB."""
        import sqlite3

        from build_db.import_jats import import_file

        xml = self.fetch_fulltext_xml(pmcid)
        if not xml:
            return {"pmcid": pmcid, "status": "no_fulltext"}
        xml_dir = Path(xml_dir)
        xml_dir.mkdir(parents=True, exist_ok=True)
        target = xml_dir / f"{pmcid.upper()}.xml"
        target.write_text(xml, encoding="utf-8")
        conn = sqlite3.connect(str(db_path))
        try:
            stats = import_file(conn, target)
            conn.commit()
        finally:
            conn.close()
        return {"pmcid": pmcid.upper(), "status": "imported", **stats}


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--search")
    parser.add_argument("--pmcid")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    client = EuropePMCClient()
    if args.search:
        results = client.search(args.search, page_size=args.limit)
        for item in results:
            print(
                json.dumps(
                    {
                        "pmcid": item.get("pmcid"),
                        "doi": item.get("doi"),
                        "title": (item.get("title") or "")[:80],
                        "isOpenAccess": item.get("isOpenAccess"),
                    },
                    ensure_ascii=False,
                )
            )
    elif args.pmcid:
        print(client.download_and_import(args.pmcid))
