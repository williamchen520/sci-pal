"""Experiments service facade: PostgreSQL by default, SQLite for tests."""

from __future__ import annotations

from . import pg_service as _pg
from .model import ProtocolNotFound, STATUSES

_PROVIDER = None


def configure(provider) -> None:
    global _PROVIDER
    _PROVIDER = provider


def _impl():
    return _PROVIDER or _pg


def list_experiments(*args, **kwargs):
    return _impl().list_experiments(*args, **kwargs)


def create_experiment(*args, **kwargs):
    return _impl().create_experiment(*args, **kwargs)


def get_experiment(*args, **kwargs):
    return _impl().get_experiment(*args, **kwargs)


def update_experiment(*args, **kwargs):
    return _impl().update_experiment(*args, **kwargs)


def list_revisions(*args, **kwargs):
    return _impl().list_revisions(*args, **kwargs)


def get_audit(*args, **kwargs):
    return _impl().get_audit(*args, **kwargs)


def create_access_request(*args, **kwargs):
    return _impl().create_access_request(*args, **kwargs)


def list_access_requests(*args, **kwargs):
    return _impl().list_access_requests(*args, **kwargs)


def decide_access_request(*args, **kwargs):
    return _impl().decide_access_request(*args, **kwargs)


def sign_experiment(*args, **kwargs):
    return _impl().sign_experiment(*args, **kwargs)


def list_signatures(*args, **kwargs):
    return _impl().list_signatures(*args, **kwargs)


def list_workspace_requests(*args, **kwargs):
    return _impl().list_workspace_requests(*args, **kwargs)
