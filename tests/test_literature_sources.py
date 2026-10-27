"""Literature source clients (mocked HTTP, no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.search import europe_pmc, metadata_sources, preprint_sources


class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload = payload
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <title>  A   preprint title </title>
    <summary>  An abstract. </summary>
    <published>2026-01-01T00:00:00Z</published>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00001v1"/>
  </entry>
</feed>
"""


class EuropePmcTests(unittest.TestCase):
    def test_search_and_fulltext(self) -> None:
        client = europe_pmc.EuropePMCClient()
        search_payload = {"resultList": {"result": [{"pmcid": "PMC1", "title": "T"}]}}
        with mock.patch.object(
            europe_pmc.requests, "get", return_value=FakeResponse(search_payload)
        ):
            results = client.search("cancer")
        self.assertEqual(results[0]["pmcid"], "PMC1")

        with mock.patch.object(
            europe_pmc.requests, "get", return_value=FakeResponse(text="<article/>")
        ):
            self.assertEqual(client.fetch_fulltext_xml("1"), "<article/>")

    def test_download_and_import_writes_file(self) -> None:
        client = europe_pmc.EuropePMCClient()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                europe_pmc.requests, "get", return_value=FakeResponse(text="<article/>")
            ), mock.patch.object(europe_pmc, "import_file", create=True):
                with mock.patch(
                    "build_db.import_jats.import_file", return_value={"sections": 1}
                ) as importer:
                    result = client.download_and_import(
                        "PMC1", xml_dir=Path(tmp), db_path=Path(tmp) / "t.db"
                    )
            self.assertEqual(result["status"], "imported")
            self.assertTrue((Path(tmp) / "PMC1.xml").exists())
            importer.assert_called_once()


class PreprintTests(unittest.TestCase):
    def test_search_arxiv(self) -> None:
        with mock.patch.object(
            preprint_sources.requests, "get", return_value=FakeResponse(text=ATOM)
        ):
            items = preprint_sources.search_arxiv("test")
        self.assertEqual(items[0]["id"], "2501.00001v1")
        self.assertEqual(items[0]["title"], "A preprint title")
        self.assertIn("pdf", items[0]["pdf_url"])

    def test_fetch_biorxiv(self) -> None:
        payload = {"collection": [{"doi": "10.1/x", "title": "T", "date": "2026-01-01"}]}
        with mock.patch.object(
            preprint_sources.requests, "get", return_value=FakeResponse(payload)
        ):
            item = preprint_sources.fetch_biorxiv("10.1/x")
        self.assertEqual(item["title"], "T")
        self.assertIn("pdf_url", item)


class MetadataTests(unittest.TestCase):
    def test_crossref_and_unpaywall(self) -> None:
        crossref = {
            "message": {
                "DOI": "10.1/x",
                "title": ["Title"],
                "container-title": ["Journal"],
                "issued": {"date-parts": [[2026]]},
                "author": [{"given": "A", "family": "B"}],
            }
        }
        with mock.patch.object(
            metadata_sources, "_get", return_value=crossref
        ):
            data = metadata_sources.crossref_work("10.1/x")
        self.assertEqual(data["title"], "Title")
        self.assertEqual(data["authors"], ["A B"])

        unpaywall = {
            "is_oa": True,
            "oa_status": "gold",
            "best_oa_location": {"url_for_pdf": "https://x/y.pdf"},
        }
        with mock.patch.object(metadata_sources, "_get", return_value=unpaywall):
            data = metadata_sources.unpaywall("10.1/x", "a@b.c")
        self.assertEqual(data["pdf_url"], "https://x/y.pdf")

    def test_core_requires_key(self) -> None:
        self.assertEqual(metadata_sources.core_search("q"), [])


if __name__ == "__main__":
    unittest.main()
