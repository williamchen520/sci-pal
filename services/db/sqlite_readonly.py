"""Opt-in SQLite query-only guard for the app database."""

from __future__ import annotations

import os
import sqlite3

_ORIGINAL_CONNECT = sqlite3.connect
_INSTALLED = False


def enabled() -> bool:
    return os.environ.get("SCIPAL_SQLITE_QUERY_ONLY", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _connect(*args, **kwargs):
    conn = _ORIGINAL_CONNECT(*args, **kwargs)
    target = str(args[0]) if args else str(kwargs.get("database", ""))
    if "research.db" in target:
        conn.execute("PRAGMA query_only=ON")
    return conn


def install() -> bool:
    global _INSTALLED
    if not enabled():
        return False
    if not _INSTALLED:
        sqlite3.connect = _connect
        _INSTALLED = True
    return True
