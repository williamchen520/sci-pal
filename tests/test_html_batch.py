"""H0 HTML batch tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.imports import html_batch


class HtmlBatchTests(unittest.TestCase):
    def test_load_manifest_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text('{"library_id":"lib","items":[{"staged_path":"a.html"}]}', encoding="utf-8")
            data = html_batch.load_manifest(path)
            self.assertEqual(data["library_id"], "lib")
            path.write_text('{"items":[]}', encoding="utf-8")
            with self.assertRaises(html_batch.BatchError):
                html_batch.load_manifest(path)

    def test_hash_and_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "a.html"
            html.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
            manifest = {
                "library_id": "lib",
                "tenant_id": "default",
                "items": [{"staged_path": str(html), "source_url": "https://example/a"}],
                "_manifest_dir": tmp,
            }
            with mock.patch.object(html_batch, "find_built_by_hash", return_value=None):
                report = html_batch.run_batch(manifest, dry_run=True)
            self.assertEqual(report["total"], 1)
            self.assertEqual(report["items"][0]["status"], "would_import")
            self.assertEqual(len(report["items"][0]["content_hash"]), 64)

    def test_duplicate_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "a.html"
            html.write_text("<html></html>", encoding="utf-8")
            manifest = {
                "library_id": "lib",
                "items": [{"staged_path": str(html)}],
                "_manifest_dir": tmp,
            }
            with mock.patch.object(
                html_batch,
                "find_built_by_hash",
                return_value={"import_id": "imp_old", "item_id": "item_0001", "status": "built"},
            ):
                report = html_batch.run_batch(manifest, dry_run=True)
            self.assertEqual(report["duplicate"], 1)
            self.assertEqual(report["items"][0]["status"], "duplicate")

    def test_missing_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "library_id": "lib",
                "items": [{"staged_path": "missing.html"}],
                "_manifest_dir": tmp,
            }
            with self.assertRaises(html_batch.BatchError):
                html_batch.run_batch(manifest, dry_run=True)


if __name__ == "__main__":
    unittest.main()
