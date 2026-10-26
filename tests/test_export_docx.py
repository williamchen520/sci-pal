"""Word (.docx) export tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docx import Document

from services.review.export_manager import ExportManager


class DocxExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.manager = ExportManager(storage_dir=Path(self.tmp.name))

    def test_export_to_docx_writes_readable_file(self) -> None:
        task = self.manager.create_export("rev_test", format="word")
        references = [{"authors": "A, B", "year": 2026, "title": "T", "journal": "J", "doi": "10.1/x"}]
        result = self.manager.export_to_docx(
            task.task_id,
            "Demo review",
            [{"title": "Introduction", "content": "First paragraph.\n\nSecond paragraph."}],
            references,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "completed")
        path = Path(result.file_path)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 1000)

        document = Document(str(path))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("Demo review", text)
        self.assertIn("Introduction", text)
        self.assertIn("First paragraph.", text)
        self.assertIn("References", text)


if __name__ == "__main__":
    unittest.main()
