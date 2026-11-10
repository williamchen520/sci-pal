from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("SCIPAL_INGEST_TRACKING", "1")

import api_server

from scripts.validate_arch import load_architecture, validate


class ArchitectureContractTests(unittest.TestCase):
    def test_architecture_json_matches_flask(self):
        if not os.environ.get("SCIPAL_PG_DSN"):
            self.skipTest("SCIPAL_PG_DSN required for ingest tracking plugin")
        arch = load_architecture(Path("ARCHITECTURE.json"))
        result = validate(arch, api_server.app)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["json_routes"], result["app_routes"])


if __name__ == "__main__":
    unittest.main()
