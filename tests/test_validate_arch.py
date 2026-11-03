from __future__ import annotations

import unittest

from flask import Flask, jsonify

from scripts.validate_arch import validate


def _app() -> Flask:
    app = Flask(__name__)

    @app.get("/api/foo/<int:item_id>")
    def get_foo(item_id: int):
        return jsonify({"id": item_id})

    return app


class ValidateArchTests(unittest.TestCase):
    def test_valid_route(self):
        arch = {
            "api": {
                "endpoints": [
                    {
                        "rule": "/api/foo/<int:item_id>",
                        "endpoint": "get_foo",
                        "methods": ["GET"],
                    }
                ]
            }
        }
        result = validate(arch, _app())
        self.assertTrue(result["ok"])

    def test_wild_route_is_rejected(self):
        arch = {"api": {"endpoints": []}}
        result = validate(arch, _app())
        self.assertFalse(result["ok"])
        self.assertTrue(any("wild route" in item for item in result["errors"]))

    def test_missing_route_is_rejected(self):
        arch = {
            "api": {
                "endpoints": [
                    {
                        "rule": "/api/missing",
                        "endpoint": "get_foo",
                        "methods": ["GET"],
                    }
                ]
            }
        }
        result = validate(arch, _app())
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing from Flask" in item for item in result["errors"]))

    def test_path_param_signature_mismatch(self):
        arch = {
            "api": {
                "endpoints": [
                    {
                        "rule": "/api/foo/<int:item_id>",
                        "endpoint": "get_foo",
                        "methods": ["GET"],
                        "parameters": ["query"],
                    }
                ]
            }
        }
        result = validate(arch, _app())
        self.assertFalse(result["ok"])
        self.assertTrue(any("does not accept parameter" in item for item in result["errors"]))

    def test_planned_route_is_allowed(self):
        arch = {
            "api": {
                "endpoints": [
                    {
                        "rule": "/api/foo/<int:item_id>",
                        "endpoint": "get_foo",
                        "methods": ["GET"],
                    },
                    {
                        "rule": "/api/planned",
                        "endpoint": "planned",
                        "methods": ["GET"],
                        "status": "planned",
                    },
                ]
            }
        }
        result = validate(arch, _app())
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
