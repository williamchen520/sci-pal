"""U2 local path import tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.imports import upload


class LocalImportTests(unittest.TestCase):
    def test_local_paths_staged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            upload, "staging_root", return_value=Path(tmp)
        ), mock.patch.object(
            upload.session,
            "create_import",
            return_value={"import_id": "imp_1", "status": "queued"},
        ) as create:
            html = Path(tmp) / "a.html"
            html.write_text("<html></html>", encoding="utf-8")
            pdf = Path(tmp) / "b.pdf"
            pdf.write_bytes(b"%PDF-1.7")
            result = upload.save_local_paths(
                [str(html), str(pdf)],
                tenant_id="default",
                library_id="lib_default",
            )
        self.assertEqual(result["import_id"], "imp_1")
        self.assertEqual(len(create.call_args.kwargs["items"]), 2)

    def test_missing_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            upload, "staging_root", return_value=Path(tmp)
        ):
            with self.assertRaises(upload.UploadError):
                upload.save_local_paths(
                    ["missing.html"], tenant_id="default", library_id="lib"
                )

    def test_extension_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            upload, "staging_root", return_value=Path(tmp)
        ):
            path = Path(tmp) / "a.exe"
            path.write_bytes(b"x")
            with self.assertRaises(upload.UploadError):
                upload.save_local_paths(
                    [str(path)], tenant_id="default", library_id="lib"
                )


if __name__ == "__main__":
    unittest.main()
