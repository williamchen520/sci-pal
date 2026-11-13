-- R8: conflict flags for grouped evidence. Human-created only.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_conflict_flags (
    flag_id      text PRIMARY KEY,
    multi_run_id text NOT NULL REFERENCES public.rag_multi_queries(multi_run_id) ON DELETE CASCADE,
    rag_id       text NOT NULL,
    note         text NOT NULL DEFAULT '',
    flagged_by   text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_conflict_flags_multi_idx
    ON public.rag_conflict_flags (multi_run_id, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rag_conflict_flags TO scipal_core_app;

COMMIT;
