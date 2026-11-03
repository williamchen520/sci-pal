from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.scaffold_from_arch import generate


class ScaffoldTests(unittest.TestCase):
    def _arch(self, tmp: Path) -> Path:
        path = tmp / "arch.json"
        path.write_text(
            json.dumps(
                {
                    "api": {
                        "endpoints": [
                            {
                                "rule": "/api/foo/<int:item_id>",
                                "endpoint": "foo.get_item",
                                "methods": ["GET"],
                                "status": "planned",
                                "codegen": {
                                    "id": "foo_get_item",
                                    "blueprint": "foo",
                                    "function": "get_item",
                                    "mcp_server": "search_server",
                                    "mcp_tool": "get_foo_item",
                                    "description": "Return one foo item.",
                                    "parameters": [
                                        {"name": "item_id", "in": "path", "type": "int"},
                                        {"name": "verbose", "in": "query", "type": "bool", "default": False},
                                    ],
                                },
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return path

    def test_generates_route_and_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = generate(self._arch(Path(tmp)), "foo_get_item")
            self.assertIn("@bp.get", files["route"])
            self.assertIn("def get_item(item_id: int, verbose: bool = False)", files["route"])
            self.assertIn("@mcp.tool", files["mcp"])
            self.assertIn("def get_foo_item(item_id: int, verbose: bool = False)", files["mcp"])
            self.assertIn('/api/foo/{item_id}', files["mcp"])

    def test_unknown_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate(self._arch(Path(tmp)), "missing")


if __name__ == "__main__":
    unittest.main()
