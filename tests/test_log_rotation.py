"""Log rotation helper tests (watchdog)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, r"D:\sciPal\scripts")

from sciPal_watchdog import _rotate_file_if_needed  # noqa: E402


class RotateLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "api.log"

    def test_small_file_is_not_rotated(self) -> None:
        self.log.write_text("small", encoding="utf-8")
        self.assertFalse(_rotate_file_if_needed(self.log, max_bytes=1024, backups=2))
        self.assertTrue(self.log.exists())

    def test_rotation_keeps_backups(self) -> None:
        self.log.write_text("x" * 100, encoding="utf-8")
        rotated = _rotate_file_if_needed(self.log, max_bytes=10, backups=2)
        self.assertTrue(rotated)
        self.assertFalse(self.log.exists())
        self.assertTrue((Path(self.tmp.name) / "api.log.1").exists())

        self.log.write_text("y" * 100, encoding="utf-8")
        _rotate_file_if_needed(self.log, max_bytes=10, backups=2)
        self.assertTrue((Path(self.tmp.name) / "api.log.1").exists())
        self.assertTrue((Path(self.tmp.name) / "api.log.2").exists())

    def test_missing_file_is_a_noop(self) -> None:
        self.assertFalse(_rotate_file_if_needed(self.log, max_bytes=10, backups=2))


if __name__ == "__main__":
    unittest.main()
