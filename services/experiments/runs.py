"""Experiment runs facade: PostgreSQL by default, SQLite for tests."""

from __future__ import annotations

from . import pg_runs as _pg

_PROVIDER = None


def configure(provider) -> None:
    global _PROVIDER
    _PROVIDER = provider


def _impl():
    return _PROVIDER or _pg


def list_runs(*args, **kwargs):
    return _impl().list_runs(*args, **kwargs)


def create_run(*args, **kwargs):
    return _impl().create_run(*args, **kwargs)


def get_run(*args, **kwargs):
    return _impl().get_run(*args, **kwargs)


def update_run(*args, **kwargs):
    return _impl().update_run(*args, **kwargs)
