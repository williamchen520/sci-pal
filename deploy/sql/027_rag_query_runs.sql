-- R5: query runs do not require a dispatched job.

BEGIN;

ALTER TABLE public.rag_runs ALTER COLUMN job_id DROP NOT NULL;
ALTER TABLE public.rag_runs ADD COLUMN IF NOT EXISTS run_type text NOT NULL DEFAULT 'job';

COMMIT;
