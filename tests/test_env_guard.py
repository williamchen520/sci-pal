"""Fail-closed environment guard tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.db.env_guard import EnvGuardError, check_env, validate_dsn


class EnvGuardTests(unittest.TestCase):
    def test_production_rejects_loopback(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_ALLOW_LOOPBACK_DSN": ""}, clear=False):
            with self.assertRaises(EnvGuardError):
                validate_dsn(
                    "SCIPAL_CORE_DSN",
                    "postgresql://u:secret@127.0.0.1:5432/scipal_core",
                    "scipal_core",
                    production=True,
                )

    def test_production_rejects_wrong_database(self) -> None:
        with self.assertRaises(EnvGuardError):
            validate_dsn(
                "SCIPAL_CORE_DSN",
                "postgresql://u:secret@db.internal:5432/scipal_rebuild",
                "scipal_core",
                production=True,
            )

    def test_loopback_override_is_explicit(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_ALLOW_LOOPBACK_DSN": "1"}, clear=False
        ):
            validate_dsn(
                "SCIPAL_CORE_DSN",
                "postgresql://u:secret@127.0.0.1:5432/scipal_core",
                "scipal_core",
                production=True,
            )

    def test_production_requires_core_and_corpus(self) -> None:
        env = {
            "SCIPAL_ENV": "production",
            "SCIPAL_PG_CORPUS_DSN": "postgresql://u:secret@db.internal:5432/scipal_rebuild",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("SCIPAL_CORE_DSN", None)
            with self.assertRaises(EnvGuardError):
                check_env()

    def test_non_production_allows_loopback(self) -> None:
        validate_dsn(
            "SCIPAL_CORE_DSN",
            "postgresql://u:secret@127.0.0.1:5432/scipal_core",
            "scipal_core",
            production=False,
        )


if __name__ == "__main__":
    unittest.main()
