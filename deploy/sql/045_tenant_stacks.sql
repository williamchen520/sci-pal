CREATE TABLE IF NOT EXISTS tenant_stacks (
    tenant_id text PRIMARY KEY,
    slug text NOT NULL UNIQUE,
    database_name text NOT NULL UNIQUE,
    storage_prefix text NOT NULL,
    index_prefix text NOT NULL,
    code_schema text NOT NULL DEFAULT 'code',
    status text NOT NULL DEFAULT 'planned',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT tenant_stacks_status CHECK (
        status IN ('planned', 'provisioned', 'failed', 'disabled')
    )
);

CREATE INDEX IF NOT EXISTS tenant_stacks_status_idx ON tenant_stacks (status);
