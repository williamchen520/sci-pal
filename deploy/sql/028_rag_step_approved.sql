-- R6.2: approved step status.

BEGIN;

ALTER TABLE public.rag_plan_steps DROP CONSTRAINT IF EXISTS rag_plan_steps_status_check;
ALTER TABLE public.rag_plan_steps ADD CONSTRAINT rag_plan_steps_status_check
    CHECK (status IN ('proposed','approved','queued','leased','running','succeeded','failed','cancelled'));

COMMIT;
