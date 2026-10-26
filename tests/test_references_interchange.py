"""RIS / EndNote XML interchange, library dedupe and routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.references import build_references_blueprint
from services.references.interchange import (
    detect_format,
    parse_endnote_xml,
    parse_ris,
    to_endnote_xml,
    to_ris,
)
from services.references.library import ReferenceLibrary

SAMPLE = {
    "title": "TLR4 signaling in sepsis",
    "authors": "Li, J; Chen, K",
    "journal": "Molecular Therapy",
    "year": 2026,
    "doi": "10.1016/j.ymthe.2026.01.001",
}


class InterchangeTests(unittest.TestCase):
    def test_ris_roundtrip(self) -> None:
        text = to_ris([SAMPLE])
        self.assertEqual(detect_format(text), "ris")
        parsed = parse_ris(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].title, SAMPLE["title"])
        self.assertEqual(parsed[0].doi, SAMPLE["doi"])
        self.assertEqual(parsed[0].authors, ["Li, J", "Chen, K"])

    def test_endnote_xml_roundtrip(self) -> None:
        text = to_endnote_xml([SAMPLE])
        self.assertEqual(detect_format(text), "endnote_xml")
        parsed = parse_endnote_xml(text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].title, SAMPLE["title"])
        self.assertEqual(parsed[0].journal, SAMPLE["journal"])

    def test_unknown_format(self) -> None:
        self.assertEqual(detect_format("hello"), "unknown")


class ExportManagerInterchangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        from services.review.export_manager import ExportManager

        self.manager = ExportManager(storage_dir=Path(self.tmp.name))

    def test_export_to_ris_writes_file(self) -> None:
        task = self.manager.create_export("rev_ris", format="ris")
        result = self.manager.export_to_ris(task.task_id, [SAMPLE])
        self.assertIsNotNone(result)
        content = Path(result.file_path).read_text(encoding="utf-8")
        self.assertIn("TY  - JOUR", content)
        self.assertIn(SAMPLE["doi"], content)

    def test_export_to_endnote_xml_writes_file(self) -> None:
        task = self.manager.create_export("rev_en", format="endnote_xml")
        result = self.manager.export_to_endnote_xml(task.task_id, [SAMPLE])
        self.assertIn("<records>", Path(result.file_path).read_text(encoding="utf-8"))


class LibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "refs.db"
        self.library = ReferenceLibrary(self.db)

    def test_import_dedupes_by_doi(self) -> None:
        refs = parse_ris(to_ris([SAMPLE, SAMPLE]))
        result = self.library.import_references(refs, source="ris")
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(self.library.count(), 1)

    def test_list_returns_rows(self) -> None:
        self.library.import_references(parse_ris(to_ris([SAMPLE])))
        rows = self.library.list()
        self.assertEqual(rows[0]["doi"], SAMPLE["doi"])


class ReferenceRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.library = ReferenceLibrary(Path(self.tmp.name) / "refs.db")
        app = Flask(__name__)
        app.register_blueprint(
            build_references_blueprint(get_library=lambda: self.library, log=app.logger)
        )
        self.client = app.test_client()

    def test_import_ris_returns_counts(self) -> None:
        response = self.client.post(
            "/api/references/import", json={"content": to_ris([SAMPLE])}
        )
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["format"], "ris")
        self.assertEqual(body["added"], 1)

    def test_empty_content_rejected(self) -> None:
        self.assertEqual(
            self.client.post("/api/references/import", json={"content": ""}).status_code, 400
        )

    def test_list_references(self) -> None:
        self.library.import_references(parse_ris(to_ris([SAMPLE])))
        body = self.client.get("/api/references").get_json()
        self.assertEqual(body["count"], 1)


if __name__ == "__main__":
    unittest.main()
