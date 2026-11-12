-- Platform library registry. Code/library modules store their own payloads
-- in their own databases; this table is only identity, scope and lifecycle.

BEGIN;

CREATE TABLE IF NOT EXISTS public.libraries (
    library_id     text PRIMARY KEY,
    owner_user_id  text NOT NULL,
    workspace_id   text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('literature','docs','code','data')),
    name           text NOT NULL,
    visibility     text NOT NULL DEFAULT 'private'
                   CHECK (visibility IN ('private','workspace','public')),
    status         text NOT NULL DEFAULT 'registered'
                   CHECK (status IN ('registered','creating','indexing','ready','failed','deleted')),
    module_id      text NOT NULL,
    config         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, name)
);

CREATE INDEX IF NOT EXISTS libraries_workspace_kind_idx
    ON public.libraries (workspace_id, kind, status);
CREATE INDEX IF NOT EXISTS libraries_owner_idx
    ON public.libraries (owner_user_id, created_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.libraries TO scipal_core_app;

COMMIT;
