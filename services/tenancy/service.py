"""Tenancy facade: PostgreSQL by default, injectable SQLite for tests."""

from __future__ import annotations

from config.settings import DATABASE_PATH

from . import pg_service as _pg
from .pg_service import ACTIONS, DEFAULT_WORKSPACE_ID, ROLE_PERMISSIONS, Membership, TenancyError

_PROVIDER = None


def configure(provider) -> None:
    """Tests inject tests.support.tenancy_sqlite here."""
    global _PROVIDER
    _PROVIDER = provider


def _impl():
    return _PROVIDER or _pg


def create_user(*args, **kwargs):
    return _impl().create_user(*args, **kwargs)


def authenticate(*args, **kwargs):
    return _impl().authenticate(*args, **kwargs)


def bootstrap_default_workspace(*args, **kwargs):
    return _impl().bootstrap_default_workspace(*args, **kwargs)


def create_workspace(*args, **kwargs):
    return _impl().create_workspace(*args, **kwargs)


def add_member(*args, **kwargs):
    return _impl().add_member(*args, **kwargs)


def get_membership(*args, **kwargs):
    return _impl().get_membership(*args, **kwargs)


def list_members(*args, **kwargs):
    return _impl().list_members(*args, **kwargs)


def list_workspaces(*args, **kwargs):
    return _impl().list_workspaces(*args, **kwargs)


def get_user_by_username(*args, **kwargs):
    return _impl().get_user_by_username(*args, **kwargs)


def get_password_hash(*args, **kwargs):
    return _impl().get_password_hash(*args, **kwargs)


def get_user(*args, **kwargs):
    return _impl().get_user(*args, **kwargs)


def authorize(*args, **kwargs):
    return _impl().authorize(*args, **kwargs)


def hash_password(*args, **kwargs):
    return _impl().hash_password(*args, **kwargs)


def verify_password(*args, **kwargs):
    return _impl().verify_password(*args, **kwargs)
