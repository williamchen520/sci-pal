-- R4: evidence ledger and artifact ledger. No vectors, no raw corpus.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_evidence (
    evidence_id    text PRIMARY KEY,
    run_id         text NOT NULL REFERENCES public.rag_runs(run_id) ON DELETE CASCADE,
    plan_id        text NOT NULL DEFAULT '',
    step_id        text NOT NULL DEFAULT '',
    rag_id         text NOT NULL,
    library_id     text NOT NULL DEFAULT '',
    snapshot       text NOT NULL DEFAULT '',
    source_path    text NOT NULL DEFAULT '',
    start_line     integer,
    end_line       integer,
    content_hash   text NOT NULL DEFAULT '',
    model_version  text NOT NULL DEFAULT '',
    score          double precision,
    metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_artifacts (
    artifact_id    text PRIMARY KEY,
    run_id         text NOT NULL REFERENCES public.rag_runs(run_id) ON DELETE CASCADE,
    kind           text NOT NULL,
    uri            text NOT NULL,
    sha256         text NOT NULL DEFAULT '',
    size_bytes     bigint,
    license        text NOT NULL DEFAULT '',
    metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_evidence_run_idx
    ON public.rag_evidence (run_id, created_at);
CREATE INDEX IF NOT EXISTS rag_artifacts_run_idx
    ON public.rag_artifacts (run_id, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.rag_evidence,
    public.rag_artifacts
TO scipal_core_app;

COMMIT;
