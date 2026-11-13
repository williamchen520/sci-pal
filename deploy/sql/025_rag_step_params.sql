-- R3: per-step execution parameters (repo path, ref, language, limit).

BEGIN;

ALTER TABLE public.rag_plan_steps
    ADD COLUMN IF NOT EXISTS params jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
