"""P3 PDF schema/cleanup contract tests."""

from __future__ import annotations

import unittest

from build_db.pg_v2_import_pdf import _clean


class PdfV2Tests(unittest.TestCase):
    def test_nul_bytes_removed(self) -> None:
        self.assertEqual(_clean("a\x00b"), "ab")
        self.assertEqual(_clean(None), None)


if __name__ == "__main__":
    unittest.main()
