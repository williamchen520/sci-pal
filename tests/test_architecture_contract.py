from __future__ import annotations

import unittest
from pathlib import Path

import api_server

from scripts.validate_arch import load_architecture, validate


class ArchitectureContractTests(unittest.TestCase):
    def test_architecture_json_matches_flask(self):
        arch = load_architecture(Path("ARCHITECTURE.json"))
        result = validate(arch, api_server.app)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["json_routes"], result["app_routes"])


if __name__ == "__main__":
    unittest.main()
