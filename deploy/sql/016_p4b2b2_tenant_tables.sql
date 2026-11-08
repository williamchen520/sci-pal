-- P4b2b2: pilot tenant copies for projects/experiments/claims.
-- public remains the rollback source.

BEGIN;

CREATE TABLE IF NOT EXISTS lib_ws_default.projects
    (LIKE public.projects INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.project_members
    (LIKE public.project_members INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiments
    (LIKE public.experiments INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiment_runs
    (LIKE public.experiment_runs INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiment_revisions
    (LIKE public.experiment_revisions INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiment_audit
    (LIKE public.experiment_audit INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiment_signatures
    (LIKE public.experiment_signatures INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.experiment_access_requests
    (LIKE public.experiment_access_requests INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.claim_cards
    (LIKE public.claim_cards INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.claim_card_evidence
    (LIKE public.claim_card_evidence INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.claim_card_events
    (LIKE public.claim_card_events INCLUDING ALL);

ALTER TABLE lib_ws_default.project_members ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.claim_card_evidence ADD COLUMN IF NOT EXISTS workspace_id TEXT;
ALTER TABLE lib_ws_default.claim_card_events ADD COLUMN IF NOT EXISTS workspace_id TEXT;

DELETE FROM lib_ws_default.projects WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.projects
SELECT * FROM public.projects WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.project_members WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.project_members
SELECT pm.*, 'ws_default'
FROM public.project_members pm
JOIN public.projects p ON p.project_id = pm.project_id
WHERE p.workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiments WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiments
SELECT * FROM public.experiments WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiment_runs WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiment_runs
SELECT * FROM public.experiment_runs WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiment_revisions WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiment_revisions
SELECT * FROM public.experiment_revisions WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiment_audit WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiment_audit
SELECT * FROM public.experiment_audit WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiment_signatures WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiment_signatures
SELECT * FROM public.experiment_signatures WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.experiment_access_requests WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.experiment_access_requests
SELECT * FROM public.experiment_access_requests WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.claim_cards WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.claim_cards
SELECT * FROM public.claim_cards WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.claim_card_evidence WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.claim_card_evidence
SELECT e.*, 'ws_default'
FROM public.claim_card_evidence e
JOIN public.claim_cards c ON c.claim_id = e.claim_id
WHERE c.workspace_id = 'ws_default';

DELETE FROM lib_ws_default.claim_card_events WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.claim_card_events
SELECT e.*, 'ws_default'
FROM public.claim_card_events e
JOIN public.claim_cards c ON c.claim_id = e.claim_id
WHERE c.workspace_id = 'ws_default';

COMMIT;
