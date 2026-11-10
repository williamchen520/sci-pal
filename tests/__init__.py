import os

os.environ.setdefault("SCIPAL_WATCH_ALLOW_SQLITE_REPO", "1")

# Runtime tenancy defaults to PG; tests inject the SQLite fixture.
import services.tenancy.service as _tenancy_service
import tests.support.tenancy_sqlite as _tenancy_sqlite

_tenancy_sqlite.TenancyError = _tenancy_service.TenancyError
_tenancy_sqlite.Membership = _tenancy_service.Membership
_tenancy_service.configure(_tenancy_sqlite)

from services.tenancy import pg_writes as _tenancy_writes
_tenancy_writes.audit_event = lambda *args, **kwargs: None


import sqlite3 as _sqlite3
import services.tenancy.permissions as _tenancy_permissions
from config.settings import DATABASE_PATH as _DATABASE_PATH


def _test_audit(workspace_id, actor_user_id, action, *, target=None, detail=None, db_path=_DATABASE_PATH):
    conn = _sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO tenancy_audit (workspace_id, actor_user_id, action, target, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (workspace_id, actor_user_id, action, target, detail),
        )
        conn.commit()
    finally:
        conn.close()


_tenancy_permissions.audit = _test_audit

import services.experiments.service as _exp_service
import services.experiments.runs as _exp_runs
import tests.support.experiments_sqlite as _exp_sqlite
import tests.support.experiments_runs_sqlite as _exp_runs_sqlite

_exp_sqlite.ProtocolNotFound = _exp_service.ProtocolNotFound
_exp_service.configure(_exp_sqlite)
_exp_runs.configure(_exp_runs_sqlite)

import services.search.ingest_tasks as _ingest_tasks
import tests.support.ingest_tasks_sqlite as _ingest_tasks_sqlite

_ingest_tasks.configure(lambda db_path: _ingest_tasks_sqlite.SqliteTaskStore(db_path))
