-- R12: reviewer assignments for grouped evidence.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_review_assignments (
    assignment_id    text PRIMARY KEY,
    multi_run_id     text NOT NULL REFERENCES public.rag_multi_queries(multi_run_id) ON DELETE CASCADE,
    rag_id           text NOT NULL,
    reviewer_user_id text NOT NULL,
    status           text NOT NULL DEFAULT 'assigned'
                     CHECK (status IN ('assigned','completed')),
    assigned_by      text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    completed_at     timestamptz,
    UNIQUE (multi_run_id, rag_id, reviewer_user_id)
);

CREATE INDEX IF NOT EXISTS rag_review_assignments_multi_idx
    ON public.rag_review_assignments (multi_run_id, status);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rag_review_assignments TO scipal_core_app;

COMMIT;
