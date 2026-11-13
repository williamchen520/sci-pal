-- R7: multi-RAG evidence groups + human adjudication.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_multi_queries (
    multi_run_id text PRIMARY KEY,
    query        text NOT NULL,
    rag_ids      jsonb NOT NULL DEFAULT '[]'::jsonb,
    library_id   text NOT NULL DEFAULT '',
    created_by   text NOT NULL DEFAULT '',
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_multi_groups (
    multi_run_id  text NOT NULL REFERENCES public.rag_multi_queries(multi_run_id) ON DELETE CASCADE,
    rag_id        text NOT NULL,
    run_id        text,
    status        text NOT NULL,
    result_count  integer NOT NULL DEFAULT 0,
    machine_signal text NOT NULL DEFAULT 'unknown',
    PRIMARY KEY (multi_run_id, rag_id)
);

CREATE TABLE IF NOT EXISTS public.rag_adjudications (
    adjudication_id text PRIMARY KEY,
    multi_run_id    text NOT NULL REFERENCES public.rag_multi_queries(multi_run_id) ON DELETE CASCADE,
    rag_id          text NOT NULL DEFAULT '*',
    decision        text NOT NULL CHECK (decision IN ('accept','reject','needs_more_evidence')),
    note            text NOT NULL DEFAULT '',
    decided_by      text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_adjudications_multi_idx
    ON public.rag_adjudications (multi_run_id, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.rag_multi_queries,
    public.rag_multi_groups,
    public.rag_adjudications
TO scipal_core_app;

COMMIT;
