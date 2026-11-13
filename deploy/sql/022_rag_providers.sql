-- RAG control plane: provider registry only. No vectors, no RAG payloads.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_providers (
    rag_id          text PRIMARY KEY,
    version         text NOT NULL,
    display_name    text NOT NULL,
    capabilities    jsonb NOT NULL DEFAULT '[]'::jsonb,
    endpoint        text NOT NULL DEFAULT '',
    database_name   text NOT NULL DEFAULT '',
    schema_version  integer NOT NULL DEFAULT 1,
    model_bindings  jsonb NOT NULL DEFAULT '{}'::jsonb,
    resource_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_residency  text NOT NULL DEFAULT 'local',
    status          text NOT NULL DEFAULT 'unknown'
                    CHECK (status IN ('active','degraded','offline','unknown')),
    manifest_hash   text NOT NULL DEFAULT '',
    manifest        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_providers_status_idx
    ON public.rag_providers (status);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rag_providers TO scipal_core_app;

COMMIT;
