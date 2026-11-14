CREATE TABLE IF NOT EXISTS import_sessions (
    import_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    library_id text NOT NULL,
    origin text NOT NULL DEFAULT 'manual',
    status text NOT NULL DEFAULT 'queued',
    total_items integer NOT NULL DEFAULT 0,
    processed_items integer NOT NULL DEFAULT 0,
    failed_items integer NOT NULL DEFAULT 0,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT import_sessions_origin CHECK (origin IN ('manual', 'dsh', 'api')),
    CONSTRAINT import_sessions_status CHECK (
        status IN ('queued', 'running', 'review', 'completed', 'partial', 'failed')
    )
);

CREATE TABLE IF NOT EXISTS import_items (
    import_id text NOT NULL,
    item_id text NOT NULL,
    kind text NOT NULL DEFAULT 'unknown',
    source_kind text NOT NULL DEFAULT 'unknown',
    source_uri text,
    content_hash text,
    status text NOT NULL DEFAULT 'received',
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (import_id, item_id),
    CONSTRAINT import_items_kind CHECK (kind IN ('paper', 'code', 'unknown')),
    CONSTRAINT import_items_status CHECK (
        status IN ('received', 'detected', 'routed', 'parsed', 'built', 'indexed',
                   'draft', 'failed', 'quarantined')
    )
);

CREATE INDEX IF NOT EXISTS import_sessions_tenant_idx ON import_sessions (tenant_id);
CREATE INDEX IF NOT EXISTS import_items_status_idx ON import_items (import_id, status);
