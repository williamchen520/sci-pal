"""U0 upload staging tests."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.datastructures import FileStorage

from services.imports import upload


def _file(name: str, data: bytes) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=name)


class UploadTests(unittest.TestCase):
    def test_valid_upload_stages_and_creates_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            upload, "staging_root", return_value=Path(tmp)
        ), mock.patch.object(
            upload.session,
            "create_import",
            return_value={"import_id": "imp_1", "status": "queued"},
        ) as create:
            result = upload.save_uploaded_files(
                [_file("../paper.html", b"<html></html>"), _file("a.pdf", b"%PDF-1.7")],
                tenant_id="default",
                library_id="lib_default",
            )
        self.assertEqual(result["import_id"], "imp_1")
        items = create.call_args.kwargs["items"]
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["staged_path"].endswith("paper.html"))
        self.assertEqual(len(items[0]["content_hash"]), 64)

    def test_extension_rejected(self) -> None:
        with self.assertRaises(upload.UploadError):
            upload.save_uploaded_files(
                [_file("a.exe", b"x")], tenant_id="default", library_id="lib"
            )

    def test_oversize_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            upload, "staging_root", return_value=Path(tmp)
        ), mock.patch.object(upload, "MAX_FILE_BYTES", 2):
            with self.assertRaises(upload.UploadError):
                upload.save_uploaded_files(
                    [_file("a.pdf", b"%PDF-1.7")],
                    tenant_id="default",
                    library_id="lib",
                )

    def test_too_many_files_rejected(self) -> None:
        with self.assertRaises(upload.UploadError):
            upload.save_uploaded_files(
                [_file(f"{i}.pdf", b"x") for i in range(51)],
                tenant_id="default",
                library_id="lib",
            )


if __name__ == "__main__":
    unittest.main()
