"""Fail-closed environment checks for PostgreSQL DSNs.

Production must not silently use loopback or the wrong database. Local tests
and development can opt into loopback explicitly.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

try:
    from psycopg.conninfo import conninfo_to_dict
except ImportError:  # pragma: no cover - psycopg is a runtime dependency
    conninfo_to_dict = None


class EnvGuardError(RuntimeError):
    pass


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
PRODUCTION_VALUES = {"prod", "production", "1", "true", "yes"}

# env name -> expected database
DSN_TARGETS = {
    "SCIPAL_CORE_DSN": "scipal_core",
    "SCIPAL_AUTH_DSN": "scipal_core",
    "SCIPAL_PG_DSN": "scipal_core",
    "SCIPAL_PG_ADMIN_DSN": "scipal_core",
    "SCIPAL_PG_TENANT_WRITE_DSN": "scipal_core",
    "SCIPAL_PG_CORPUS_DSN": "scipal_rebuild",
    "SCIPAL_PG_MAIN_READ_DSN": "scipal_rebuild",
    "SCIPAL_PG_OWNER_DSN": "scipal_rebuild",
    "SCIPAL_PG_INGEST_DSN": "scipal_rebuild",
}


def is_production() -> bool:
    return os.environ.get("SCIPAL_ENV", "").strip().lower() in PRODUCTION_VALUES


def _parse(dsn: str) -> dict[str, str]:
    if conninfo_to_dict is None:
        parsed = urlparse(dsn)
        return {
            "host": parsed.hostname or "",
            "dbname": (parsed.path or "").lstrip("/"),
        }
    try:
        values = conninfo_to_dict(dsn)
    except Exception as exc:  # noqa: BLE001
        raise EnvGuardError(f"invalid DSN: {exc}") from None
    return {key: str(value) for key, value in values.items() if value is not None}


def validate_dsn(name: str, dsn: str, expected_db: str, *, production: bool) -> None:
    if not dsn.strip():
        if production:
            raise EnvGuardError(f"{name} is required in production")
        return
    parsed = _parse(dsn)
    dbname = parsed.get("dbname", "")
    if expected_db and dbname != expected_db:
        raise EnvGuardError(
            f"{name} points to database {dbname!r}; expected {expected_db!r}"
        )
    host = parsed.get("host", "").lower()
    allow_loopback = os.environ.get("SCIPAL_ALLOW_LOOPBACK_DSN") == "1"
    if production and host in LOOPBACK_HOSTS and not allow_loopback:
        raise EnvGuardError(
            f"{name} uses loopback host {host!r} in production; "
            "set SCIPAL_ALLOW_LOOPBACK_DSN=1 only for local tests"
        )
    password = parsed.get("password", "")
    if production and password == "scipal":
        raise EnvGuardError(f"{name} uses the default 'scipal' password")


def check_env() -> None:
    """Validate all configured DSNs when SCIPAL_ENV=production."""
    if not is_production():
        return
    required = {"SCIPAL_CORE_DSN", "SCIPAL_PG_CORPUS_DSN"}
    for name, expected_db in DSN_TARGETS.items():
        dsn = os.environ.get(name, "")
        if not dsn:
            if name in required:
                raise EnvGuardError(f"{name} is required in production")
            continue
        validate_dsn(name, dsn, expected_db, production=True)
