"""Ingest write backend factory: PG by default, SQLite for tests."""

from __future__ import annotations

_FACTORY = None


def configure(factory) -> None:
    global _FACTORY
    _FACTORY = factory


def writer_for(db_path):
    return _FACTORY(db_path) if _FACTORY else None
