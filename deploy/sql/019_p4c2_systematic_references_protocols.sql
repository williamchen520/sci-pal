-- P4c2: tenant copies for systematic/references/protocols.

BEGIN;

CREATE TABLE IF NOT EXISTS lib_ws_default.review_projects (LIKE public.review_projects INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.review_project_papers (LIKE public.review_project_papers INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.review_project_members (LIKE public.review_project_members INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.screening_decisions (LIKE public.screening_decisions INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.adjudications (LIKE public.adjudications INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.evidence_rows (LIKE public.evidence_rows INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.risk_of_bias (LIKE public.risk_of_bias INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.review_webhooks (LIKE public.review_webhooks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.review_events (LIKE public.review_events INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.reference_library (LIKE public.reference_library INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.protocol_imports (LIKE public.protocol_imports INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.protocol_runs (LIKE public.protocol_runs INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.protocol_steps (LIKE public.protocol_steps INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.protocol_run_files (LIKE public.protocol_run_files INCLUDING ALL);

ALTER TABLE lib_ws_default.review_projects ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.review_project_papers ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.review_project_members ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.screening_decisions ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.adjudications ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.evidence_rows ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.risk_of_bias ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.review_webhooks ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.review_events ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.reference_library ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.protocol_imports ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.protocol_runs ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.protocol_steps ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.protocol_run_files ADD COLUMN IF NOT EXISTS workspace_id TEXT;

DELETE FROM lib_ws_default.review_projects;
INSERT INTO lib_ws_default.review_projects SELECT *, 'ws_default' FROM public.review_projects;
DELETE FROM lib_ws_default.review_project_papers;
INSERT INTO lib_ws_default.review_project_papers SELECT *, 'ws_default' FROM public.review_project_papers;
DELETE FROM lib_ws_default.review_project_members;
INSERT INTO lib_ws_default.review_project_members SELECT *, 'ws_default' FROM public.review_project_members;
DELETE FROM lib_ws_default.screening_decisions;
INSERT INTO lib_ws_default.screening_decisions SELECT *, 'ws_default' FROM public.screening_decisions;
DELETE FROM lib_ws_default.adjudications;
INSERT INTO lib_ws_default.adjudications SELECT *, 'ws_default' FROM public.adjudications;
DELETE FROM lib_ws_default.evidence_rows;
INSERT INTO lib_ws_default.evidence_rows SELECT *, 'ws_default' FROM public.evidence_rows;
DELETE FROM lib_ws_default.risk_of_bias;
INSERT INTO lib_ws_default.risk_of_bias SELECT *, 'ws_default' FROM public.risk_of_bias;
DELETE FROM lib_ws_default.review_webhooks;
INSERT INTO lib_ws_default.review_webhooks SELECT *, 'ws_default' FROM public.review_webhooks;
DELETE FROM lib_ws_default.review_events;
INSERT INTO lib_ws_default.review_events SELECT *, 'ws_default' FROM public.review_events;
DELETE FROM lib_ws_default.reference_library;
INSERT INTO lib_ws_default.reference_library SELECT *, 'ws_default' FROM public.reference_library;
DELETE FROM lib_ws_default.protocol_imports;
INSERT INTO lib_ws_default.protocol_imports SELECT *, 'ws_default' FROM public.protocol_imports;
DELETE FROM lib_ws_default.protocol_runs;
INSERT INTO lib_ws_default.protocol_runs SELECT *, 'ws_default' FROM public.protocol_runs;
DELETE FROM lib_ws_default.protocol_steps;
INSERT INTO lib_ws_default.protocol_steps SELECT *, 'ws_default' FROM public.protocol_steps;
DELETE FROM lib_ws_default.protocol_run_files;
INSERT INTO lib_ws_default.protocol_run_files SELECT *, 'ws_default' FROM public.protocol_run_files;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lib_ws_default TO scipal_tenant_writer;

COMMIT;
