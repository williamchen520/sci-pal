-- R13: finalization gate + content seal hash. Not a cryptographic signature.

BEGIN;

ALTER TABLE public.rag_multi_queries
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','finalized')),
    ADD COLUMN IF NOT EXISTS finalized_by text,
    ADD COLUMN IF NOT EXISTS finalized_at timestamptz;

CREATE TABLE IF NOT EXISTS public.rag_multi_finalizations (
    finalization_id text PRIMARY KEY,
    multi_run_id    text NOT NULL REFERENCES public.rag_multi_queries(multi_run_id) ON DELETE CASCADE,
    decision        text NOT NULL CHECK (decision IN ('accepted','rejected','needs_more_evidence')),
    note            text NOT NULL DEFAULT '',
    finalized_by    text NOT NULL,
    content_hash    text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_multi_finalizations_run_idx
    ON public.rag_multi_finalizations (multi_run_id, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rag_multi_finalizations TO scipal_core_app;

COMMIT;
