"""PostgreSQL experiments service facade for runtime."""

from __future__ import annotations

from . import pg_read, pg_write
from .model import STATUSES, ProtocolNotFound


def list_experiments(project_id, workspace_id, user_id, **_):
    return pg_read.list_experiments(project_id, workspace_id, user_id)


def get_experiment(experiment_id, workspace_id, user_id, **_):
    return pg_read.get_experiment(experiment_id, workspace_id, user_id)


def list_revisions(experiment_id, workspace_id, user_id, **_):
    return pg_read.list_revisions(experiment_id, workspace_id, user_id)


def get_audit(experiment_id, workspace_id, user_id, **_):
    return pg_read.get_audit(experiment_id, workspace_id, user_id)


def list_signatures(experiment_id, workspace_id, user_id, **_):
    return pg_read.list_signatures(experiment_id, workspace_id, user_id)


def list_access_requests(experiment_id, workspace_id, user_id, **_):
    return pg_read.list_access_requests(experiment_id, workspace_id, user_id)


def list_workspace_requests(workspace_id, user_id, **_):
    return pg_read.list_workspace_requests(workspace_id, user_id)


def create_experiment(*args, **kwargs):
    kwargs.pop("db_path", None)
    return pg_write.create_experiment(*args, **kwargs)


def update_experiment(*args, **kwargs):
    kwargs.pop("db_path", None)
    return pg_write.update_experiment(*args, **kwargs)


def create_access_request(*args, **kwargs):
    kwargs.pop("db_path", None)
    return pg_write.create_access_request(*args, **kwargs)


def decide_access_request(*args, **kwargs):
    kwargs.pop("db_path", None)
    return pg_write.decide_access_request(*args, **kwargs)


def sign_experiment(*args, **kwargs):
    kwargs.pop("db_path", None)
    return pg_write.sign_experiment(*args, **kwargs)
