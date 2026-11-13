-- R10: workspace scope + reviewer role for evidence adjudication.

BEGIN;

ALTER TABLE public.rag_multi_queries
    ADD COLUMN IF NOT EXISTS workspace_id text NOT NULL DEFAULT 'ws_default';

CREATE INDEX IF NOT EXISTS rag_multi_queries_workspace_idx
    ON public.rag_multi_queries (workspace_id, created_at);

COMMIT;
