-- P4b2b3: tenant copies for tasks/watch.

BEGIN;

CREATE TABLE IF NOT EXISTS lib_ws_default.tasks
    (LIKE public.tasks INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.watch_profiles
    (LIKE public.watch_profiles INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.watch_runs
    (LIKE public.watch_runs INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.watch_items
    (LIKE public.watch_items INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.watch_seen
    (LIKE public.watch_seen INCLUDING ALL);
CREATE TABLE IF NOT EXISTS lib_ws_default.watch_profile_journals
    (LIKE public.watch_profile_journals INCLUDING ALL);

DELETE FROM lib_ws_default.tasks WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.tasks
SELECT * FROM public.tasks WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.watch_profiles WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.watch_profiles
SELECT * FROM public.watch_profiles WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.watch_runs WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.watch_runs
SELECT * FROM public.watch_runs WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.watch_items WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.watch_items
SELECT * FROM public.watch_items WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.watch_seen WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.watch_seen
SELECT * FROM public.watch_seen WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.watch_profile_journals WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.watch_profile_journals
SELECT * FROM public.watch_profile_journals WHERE workspace_id = 'ws_default';

GRANT SELECT ON lib_ws_default.tasks TO scipal_main_reader;
GRANT SELECT ON lib_ws_default.watch_profiles TO scipal_main_reader;
GRANT SELECT ON lib_ws_default.watch_runs TO scipal_main_reader;
GRANT SELECT ON lib_ws_default.watch_items TO scipal_main_reader;
GRANT SELECT ON lib_ws_default.watch_seen TO scipal_main_reader;
GRANT SELECT ON lib_ws_default.watch_profile_journals TO scipal_main_reader;

COMMIT;
