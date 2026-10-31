"""Cross-platform path regression tests."""

from __future__ import annotations

import os
import re
import unittest

from config.paths import DATA_DIR, DB_PATH, LOGS_DIR, MODELS_DIR, PROJECT_ROOT


class PathConfigTests(unittest.TestCase):
    def test_project_root_contains_app(self) -> None:
        self.assertTrue((PROJECT_ROOT / "api_server.py").is_file())
        self.assertTrue(DB_PATH.is_absolute())
        self.assertTrue(LOGS_DIR.is_absolute())

    def test_default_data_and_models_are_project_relative(self) -> None:
        if os.environ.get("SCIPAL_DATA_DIR") or os.environ.get("SCIPAL_MODELS_DIR"):
            self.skipTest("explicit path overrides are in use")
        self.assertEqual(DATA_DIR, PROJECT_ROOT / "data")
        self.assertEqual(MODELS_DIR, PROJECT_ROOT / "models")

    def test_runtime_modules_have_no_windows_drive_literals(self) -> None:
        pattern = re.compile(r"[A-Za-z]:\\\\")
        offenders = []
        for path in sorted((PROJECT_ROOT / "services").rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
