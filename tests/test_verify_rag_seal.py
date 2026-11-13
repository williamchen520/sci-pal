"""Standalone sealed-package verification test."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts import verify_rag_seal
from services.rag_control.signing import sign


class VerifyPackageTests(unittest.TestCase):
    def _package(self, tamper: bool = False) -> str:
        canonical = b'{"x":1}'
        digest = hashlib.sha256(canonical).hexdigest()
        seal = sign(digest)
        final = {
            "content_hash": digest,
            "signature": seal["signature"],
            "public_key": seal["public_key"],
            "key_id": seal["key_id"],
            "signed_at": "2026-01-01T00:00:00+00:00",
            "timestamp_source": "local_clock",
        }
        fd, name = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        path = Path(name)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("data/finalization.json", json.dumps(final))
            archive.writestr("data/canonical.json", canonical + (b"!" if tamper else b""))
        return str(path)

    def test_valid_package(self) -> None:
        path = self._package()
        with mock.patch.object(sys, "argv", ["verify", path]), mock.patch("builtins.print"):
            self.assertEqual(verify_rag_seal.main(), 0)
        Path(path).unlink()

    def test_tampered_package(self) -> None:
        path = self._package(tamper=True)
        with mock.patch.object(sys, "argv", ["verify", path]), mock.patch("builtins.print"):
            self.assertEqual(verify_rag_seal.main(), 1)
        Path(path).unlink()


if __name__ == "__main__":
    unittest.main()
