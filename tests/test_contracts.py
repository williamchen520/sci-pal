"""Unit tests for the response contracts (no database, no models)."""

from __future__ import annotations

import json
import sqlite3
import unittest

from contracts import (
    AppError,
    Conflict,
    ErrorKind,
    InternalError,
    InvalidInput,
    NotFound,
    UpstreamTimeout,
    fail,
    from_exception,
    is_ok,
    ok,
)
from contracts.envelope import SCHEMA_VERSION


class EnvelopeTests(unittest.TestCase):
    def test_ok_shape(self) -> None:
        env = ok({"count": 3})
        self.assertEqual(
            set(env), {"schema_version", "ok", "data", "error", "context"}
        )
        self.assertEqual(env["schema_version"], SCHEMA_VERSION)
        self.assertTrue(env["ok"])
        self.assertEqual(env["data"], {"count": 3})
        self.assertIsNone(env["error"])
        self.assertTrue(is_ok(env))

    def test_ok_context_drops_none(self) -> None:
        env = ok(None, run_id="r1", elapsed_ms=None)
        self.assertEqual(env["context"], {"run_id": "r1"})

    def test_fail_from_app_error(self) -> None:
        env = fail(NotFound("paper not found", source="research.db"))
        self.assertFalse(env["ok"])
        self.assertIsNone(env["data"])
        self.assertEqual(env["error"]["kind"], "not_found")
        self.assertEqual(env["error"]["source"], "research.db")
        self.assertFalse(env["error"]["retryable"])

    def test_fail_accepts_mapping(self) -> None:
        env = fail({"kind": "conflict", "message": "duplicate"})
        self.assertEqual(env["error"]["kind"], "conflict")

    def test_fail_rejects_unknown_kind(self) -> None:
        with self.assertRaises(ValueError):
            fail({"kind": "boom", "message": "x"})

    def test_envelope_is_json_serializable(self) -> None:
        json.dumps(ok({"a": 1}, run_id="r1"))


class ErrorTests(unittest.TestCase):
    def test_status_mapping(self) -> None:
        self.assertEqual(NotFound("x").status, 404)
        self.assertEqual(InvalidInput("x").status, 400)
        self.assertEqual(Conflict("x").status, 409)
        self.assertEqual(UpstreamTimeout("x").status, 504)
        self.assertEqual(InternalError().status, 500)

    def test_retryable_defaults(self) -> None:
        self.assertTrue(UpstreamTimeout("x").retryable)
        self.assertFalse(NotFound("x").retryable)
        self.assertFalse(UpstreamTimeout("x", retryable=False).retryable)

    def test_from_exception_passthrough(self) -> None:
        original = NotFound("x")
        self.assertIs(from_exception(original), original)

    def test_from_exception_mapping(self) -> None:
        self.assertEqual(from_exception(ValueError("bad")).kind, ErrorKind.INVALID_INPUT)
        self.assertEqual(from_exception(TimeoutError()).kind, ErrorKind.TIMEOUT)
        self.assertEqual(
            from_exception(sqlite3.OperationalError("locked")).kind,
            ErrorKind.INTERNAL,
        )
        self.assertEqual(from_exception(RuntimeError("boom")).kind, ErrorKind.INTERNAL)

    def test_generic_exception_hides_message(self) -> None:
        err = from_exception(RuntimeError("secret path C:/x"))
        self.assertNotIn("secret", err.message)
        self.assertIsInstance(err.__cause__, RuntimeError)

    def test_payload_has_no_cause(self) -> None:
        payload = AppError(ErrorKind.INTERNAL, "boom", cause=RuntimeError("x")).to_payload()
        self.assertNotIn("cause", payload)


class FlaskBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from flask import Flask
        except ImportError:  # pragma: no cover
            self.skipTest("flask not installed")
        from contracts.flask_binding import register_error_handlers

        self.app = Flask(__name__)
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        register_error_handlers(self.app)

        @self.app.get("/missing")
        def missing():
            raise NotFound("paper not found")

        @self.app.get("/bad")
        def bad():
            raise ValueError("bad parameter")

        @self.app.get("/crash")
        def crash():
            raise RuntimeError("secret internals")

        @self.app.get("/boom")
        def boom():
            raise Conflict("duplicate")

        self.client = self.app.test_client()

    def test_not_found(self) -> None:
        resp = self.client.get("/missing")
        self.assertEqual(resp.status_code, 404)
        body = resp.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["kind"], "not_found")

    def test_invalid_value(self) -> None:
        resp = self.client.get("/bad")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["kind"], "invalid_input")

    def test_unexpected_hides_details(self) -> None:
        resp = self.client.get("/crash")
        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertEqual(body["error"]["message"], "Internal error")
        self.assertNotIn("secret", json.dumps(body))

    def test_conflict(self) -> None:
        resp = self.client.get("/boom")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["error"]["kind"], "conflict")

    def test_unknown_route_uses_http_mapping(self) -> None:
        resp = self.client.get("/nope")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"]["kind"], "not_found")


if __name__ == "__main__":
    unittest.main()
