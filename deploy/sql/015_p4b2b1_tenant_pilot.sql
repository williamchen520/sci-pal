-- P4b2b1: pilot tenant copies of reviews/notes.
-- public tables remain the rollback source.

BEGIN;

CREATE TABLE IF NOT EXISTS lib_ws_default.reviews
    (LIKE public.reviews INCLUDING ALL);

CREATE TABLE IF NOT EXISTS lib_ws_default.notes
    (LIKE public.notes INCLUDING ALL);

DELETE FROM lib_ws_default.reviews WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.reviews
SELECT * FROM public.reviews WHERE workspace_id = 'ws_default';

DELETE FROM lib_ws_default.notes WHERE workspace_id = 'ws_default';
INSERT INTO lib_ws_default.notes
SELECT * FROM public.notes WHERE workspace_id = 'ws_default';

COMMIT;
