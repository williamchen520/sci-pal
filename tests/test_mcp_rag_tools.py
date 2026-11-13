"""DSH MCP RAG tool tests (no network)."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from mcp_server import code_server


class RagToolTests(unittest.TestCase):
    def test_api_requires_token(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(code_server.ToolError):
                code_server._api("/api/rag/plans")

    def test_rag_plan_posts_steps(self) -> None:
        with mock.patch.object(code_server, "_api", return_value={"plan_id": "p", "plan_hash": "h"}) as api:
            result = json.loads(code_server.rag_plan("intent", '[{"action":"rag_query","rag_id":"code"}]'))
        self.assertEqual(result["plan_id"], "p")
        api.assert_called_once()

    def test_dispatch_has_no_approve(self) -> None:
        self.assertFalse(hasattr(code_server, "rag_approve"))


if __name__ == "__main__":
    unittest.main()
