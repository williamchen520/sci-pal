"""R3 worker command/path tests (no network)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.rag_worker as worker


class RagWorkerTests(unittest.TestCase):
    def test_safe_repo_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(worker, "REPO_ROOT", root):
                inside = root / "repo"
                inside.mkdir()
                self.assertEqual(worker._safe_repo(str(inside)), inside.resolve())
                with self.assertRaises(ValueError):
                    worker._safe_repo(str(root.parent))

    def test_command_uses_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            with mock.patch.object(worker, "REPO_ROOT", root):
                command = worker._command(
                    {
                        "repo_path": str(repo),
                        "library_id": "lib",
                        "repo_url": "https://example/repo",
                        "ref": "v1",
                        "language": "nextflow",
                        "limit": 10,
                    }
                )
        self.assertIn("code_rag.ingest", command)
        self.assertIn("--language", command)
        self.assertIn("nextflow", command)


if __name__ == "__main__":
    unittest.main()
