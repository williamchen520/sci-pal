"""N0.7 code index automation tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.imports import code_lane


class CodeIndexTests(unittest.TestCase):
    def test_index_success(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_CODE_DSN": "postgresql://x"}), mock.patch(
            "code_rag.index.index_library",
            return_value={"units": 3, "dim": 384},
        ):
            result = code_lane._index_code(
                {"library_id": "lib_default"}, {"snapshot_id": "snap_1"}
            )
        self.assertEqual(result["status"], "indexed")
        self.assertEqual(result["units"], 3)

    def test_index_failure_does_not_raise(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_CODE_DSN": "postgresql://x"}), mock.patch(
            "code_rag.index.index_library", side_effect=RuntimeError("cuda missing")
        ):
            result = code_lane._index_code(
                {"library_id": "lib_default"}, {"snapshot_id": "snap_1"}
            )
        self.assertEqual(result["status"], "error")
        self.assertIn("cuda", result["error"])

    def test_index_skipped_without_dsn(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_CODE_DSN": ""}):
            result = code_lane._index_code({"library_id": "lib_default"}, {})
        self.assertEqual(result["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
