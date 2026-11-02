-- Phase 0 schema parity: projects / experiments and experiment_runs columns.
-- Additive only. Safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    data_class TEXT NOT NULL DEFAULT 'internal',
    copied_from TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS projects_workspace_idx ON projects (workspace_id);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id)
);
CREATE INDEX IF NOT EXISTS project_members_user_idx ON project_members (user_id);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    protocol_id TEXT,
    protocol_version TEXT,
    content TEXT DEFAULT '',
    data_class TEXT NOT NULL DEFAULT 'private',
    current_revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS experiments_project_idx ON experiments (project_id);
CREATE INDEX IF NOT EXISTS experiments_workspace_idx ON experiments (workspace_id);

CREATE TABLE IF NOT EXISTS experiment_revisions (
    revision_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (experiment_id, revision)
);
CREATE INDEX IF NOT EXISTS experiment_revisions_experiment_idx ON experiment_revisions (experiment_id);

CREATE TABLE IF NOT EXISTS experiment_signatures (
    signature_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    signer_user_id TEXT NOT NULL,
    meaning TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    signature_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS experiment_signatures_experiment_idx ON experiment_signatures (experiment_id);

CREATE TABLE IF NOT EXISTS experiment_audit (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    revision INTEGER,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS experiment_audit_experiment_idx ON experiment_audit (experiment_id);

CREATE TABLE IF NOT EXISTS experiment_access_requests (
    request_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    requester_user_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    scope TEXT NOT NULL DEFAULT 'read',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS experiment_access_requests_experiment_idx
    ON experiment_access_requests (experiment_id);

ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS experiment_id TEXT;
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS owner_user_id TEXT;
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS planned_json TEXT DEFAULT '{}';
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS actual_json TEXT DEFAULT '{}';
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS observations TEXT DEFAULT '';
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS started_at TEXT;
ALTER TABLE experiment_runs ADD COLUMN IF NOT EXISTS ended_at TEXT;
CREATE INDEX IF NOT EXISTS experiment_runs_experiment_idx ON experiment_runs (experiment_id);

COMMIT;
