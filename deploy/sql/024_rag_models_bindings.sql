-- R2: model registry and index binding. No vectors, no model weights.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_models (
    model_id        text PRIMARY KEY,
    provider        text NOT NULL DEFAULT 'local',
    kind            text NOT NULL CHECK (kind IN ('embedding','rerank','generation')),
    dimension       integer,
    context_window  integer,
    endpoint        text NOT NULL DEFAULT '',
    license         text NOT NULL DEFAULT '',
    cost_profile    jsonb NOT NULL DEFAULT '{}'::jsonb,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','degraded','offline','unknown')),
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_index_bindings (
    binding_id      text PRIMARY KEY,
    rag_id          text NOT NULL,
    library_id      text NOT NULL,
    index_name      text NOT NULL,
    embedding_model text NOT NULL,
    dimension       integer NOT NULL,
    schema_version  integer NOT NULL DEFAULT 1,
    snapshot        text NOT NULL DEFAULT '',
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','building','stale','failed')),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rag_id, library_id, index_name)
);

CREATE INDEX IF NOT EXISTS rag_index_bindings_library_idx
    ON public.rag_index_bindings (rag_id, library_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.rag_models,
    public.rag_index_bindings
TO scipal_core_app;

COMMIT;
