"""Hard runtime guard against SQLite in production.

Tests and development may still use SQLite; production sets
``SCIPAL_SQLITE_RUNTIME=0`` and any residual sqlite3.connect fails loudly.
"""

from __future__ import annotations

import logging
import os
import sqlite3

LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def runtime_disabled() -> bool:
    raw = os.environ.get("SCIPAL_SQLITE_RUNTIME", "").strip().lower()
    return raw in {"0", "false", "off", "no", "deny", "disabled"}


def install_sqlite_guard() -> None:
    global _INSTALLED
    if _INSTALLED or not runtime_disabled():
        return
    original = sqlite3.connect

    def denied(*args, **kwargs):
        raise RuntimeError(
            "SQLite runtime is disabled (SCIPAL_SQLITE_RUNTIME=0); "
            "use PostgreSQL. This call indicates a remaining SQLite fallback."
        )

    sqlite3.connect = denied
    _INSTALLED = True
    LOGGER.warning("SQLite runtime guard installed; sqlite3.connect is denied")
    _ = original
