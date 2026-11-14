CREATE TABLE IF NOT EXISTS federation_catalog (
    catalog_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    library_id text NOT NULL,
    source_kind text NOT NULL DEFAULT 'paper',
    target_kind text NOT NULL DEFAULT 'main',
    target_tenant_id text,
    allowed_scopes text[] NOT NULL DEFAULT ARRAY['own']::text[],
    db_ref text,
    index_name text,
    status text NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT federation_catalog_target_main CHECK (target_kind = 'main'),
    CONSTRAINT federation_catalog_no_peer CHECK (target_tenant_id IS NULL),
    CONSTRAINT federation_catalog_scopes CHECK (
        allowed_scopes <@ ARRAY['own', 'main', 'both']::text[]
    ),
    CONSTRAINT federation_catalog_unique_library UNIQUE (tenant_id, library_id)
);

CREATE INDEX IF NOT EXISTS federation_catalog_tenant_idx
    ON federation_catalog (tenant_id);
