"""PDF export tests (reportlab, no LibreOffice)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.review.export_manager import ExportManager


class PdfExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.manager = ExportManager(storage_dir=Path(self.tmp.name))

    def test_export_to_pdf_writes_valid_file(self) -> None:
        task = self.manager.create_export("rev_pdf", format="pdf")
        result = self.manager.export_to_pdf(
            task.task_id,
            "Demo review",
            [{"title": "Introduction", "content": "First paragraph.\n\nSecond paragraph."}],
            [{"authors": "A, B", "year": 2026, "title": "T", "journal": "J", "doi": "10.1/x"}],
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "completed")
        path = Path(result.file_path)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 1000)
        self.assertEqual(path.read_bytes()[:5], b"%PDF-")


if __name__ == "__main__":
    unittest.main()
