"""Tests for the independent code-rag HTTP service."""

from __future__ import annotations

import unittest
from unittest import mock

from code_rag.api import create_app


class CodeRagApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app().test_client()

    def test_health(self) -> None:
        with mock.patch("code_rag.api.health", return_value={"ok": True, "units": 1}):
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_search_rejects_empty_query(self) -> None:
        response = self.client.post("/libraries/lib_1/search", json={"query": ""})
        self.assertEqual(response.status_code, 400)

    def test_search_returns_hits(self) -> None:
        with mock.patch("code_rag.api._search", return_value=[{"symbol_name": "f"}]):
            response = self.client.post("/libraries/lib_1/search", json={"query": "f"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["hits"][0]["symbol_name"], "f")

    def test_trace_requires_unit(self) -> None:
        response = self.client.get("/libraries/lib_1/trace")
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
