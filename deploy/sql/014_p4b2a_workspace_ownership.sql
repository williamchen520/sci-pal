-- P4b2a: add workspace ownership to reviews/tasks/watch tables.
-- Additive; default is ws_default for existing single-workspace deployment.

BEGIN;

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS workspace_id TEXT;

ALTER TABLE watch_profiles ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE watch_runs ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE watch_items ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE watch_seen ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE watch_profile_journals ADD COLUMN IF NOT EXISTS workspace_id TEXT;

UPDATE reviews SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE tasks SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE watch_profiles SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE watch_runs SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE watch_items SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE watch_seen SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;
UPDATE watch_profile_journals SET workspace_id = 'ws_default' WHERE workspace_id IS NULL;

ALTER TABLE reviews ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE tasks ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE watch_profiles ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE watch_runs ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE watch_items ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE watch_seen ALTER COLUMN workspace_id SET DEFAULT 'ws_default';
ALTER TABLE watch_profile_journals ALTER COLUMN workspace_id SET DEFAULT 'ws_default';

ALTER TABLE reviews ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE tasks ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE watch_profiles ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE watch_runs ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE watch_items ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE watch_seen ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE watch_profile_journals ALTER COLUMN workspace_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reviews_workspace ON reviews (workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks (workspace_id);
CREATE INDEX IF NOT EXISTS idx_watch_profiles_workspace ON watch_profiles (workspace_id);
CREATE INDEX IF NOT EXISTS idx_watch_runs_workspace ON watch_runs (workspace_id);
CREATE INDEX IF NOT EXISTS idx_watch_items_workspace ON watch_items (workspace_id);
CREATE INDEX IF NOT EXISTS idx_watch_seen_workspace ON watch_seen (workspace_id);
CREATE INDEX IF NOT EXISTS idx_watch_profile_journals_workspace ON watch_profile_journals (workspace_id);

COMMIT;
