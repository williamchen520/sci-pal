"""LLM timeout/retry behaviour: a hung Ollama call must fail fast, not hang a run."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from services.review.llm_client import LLMClient, LLMError


class LLMTimeoutTests(unittest.TestCase):
    def _client(self) -> LLMClient:
        return LLMClient(timeout=1, max_retries=2, retry_delay=0)

    def test_timeout_is_retried_then_raised(self) -> None:
        client = self._client()
        calls = []

        def fake_post(*args, **kwargs):
            calls.append(kwargs.get("timeout"))
            raise requests.Timeout("simulated hang")

        with patch.object(client, "is_available", return_value=True), patch(
            "services.review.llm_client.requests.post", side_effect=fake_post
        ), patch("services.review.llm_client.time.sleep"):
            with self.assertRaises(LLMError) as ctx:
                client.chat("sys", "user")

        self.assertEqual(len(calls), 2)
        self.assertIn("超时", str(ctx.exception))
        self.assertIn("ollama stop", str(ctx.exception))

    def test_generic_error_keeps_retry_message(self) -> None:
        client = self._client()

        with patch.object(client, "is_available", return_value=True), patch(
            "services.review.llm_client.requests.post", side_effect=RuntimeError("boom")
        ), patch("services.review.llm_client.time.sleep"):
            with self.assertRaises(LLMError) as ctx:
                client.chat("sys", "user")

        self.assertIn("boom", str(ctx.exception))

    def test_defaults_come_from_env(self) -> None:
        import os

        with patch.dict(os.environ, {"SCIPAL_LLM_TIMEOUT": "42", "SCIPAL_LLM_RETRIES": "3"}):
            client = LLMClient()
        self.assertEqual(client.timeout, 42)
        self.assertEqual(client.max_retries, 3)


if __name__ == "__main__":
    unittest.main()
