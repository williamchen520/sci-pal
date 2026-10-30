"""Domain pack loader, validator and API tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.domain_packs import build_domain_packs_blueprint
from services.domain_packs import get_pack, list_packs, load_pack, validate_pack


class DomainPackTests(unittest.TestCase):
    def test_builtin_pack_loads_and_validates(self) -> None:
        pack = get_pack("biomed.oncoimmuno")
        self.assertIsNotNone(pack)
        self.assertEqual(pack.version, "0.1.0")
        self.assertGreaterEqual(len(pack.taxonomy.get("terms") or []), 10)
        self.assertIn("claim_text", pack.evidence_schema.get("fields") or {})
        self.assertTrue(pack.prompts.get("review"))
        result = validate_pack(pack.path)
        self.assertTrue(result["ok"], result)

    def test_malformed_pack_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bad"
            root.mkdir()
            (root / "pack.yaml").write_text("id: bad\nversion: 0.1.0\n", encoding="utf-8")
            result = validate_pack(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("discipline" in error for error in result["errors"]))
            with self.assertRaises(ValueError):
                load_pack(root)

    def test_pack_list_contains_builtin(self) -> None:
        self.assertIn("biomed.oncoimmuno", {pack.id for pack in list_packs()})


class DomainPackRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_domain_packs_blueprint())
        self.client = app.test_client()

    def test_list_detail_validate(self) -> None:
        listing = self.client.get("/api/domain-packs").get_json()["packs"]
        self.assertTrue(listing)
        detail = self.client.get("/api/domain-packs/biomed.oncoimmuno")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["id"], "biomed.oncoimmuno")
        result = self.client.get("/api/domain-packs/biomed.oncoimmuno/validate")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.get_json()["ok"])

    def test_missing_pack(self) -> None:
        self.assertEqual(
            self.client.get("/api/domain-packs/nope").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
