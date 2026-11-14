CREATE TABLE IF NOT EXISTS paper_sources (
    source_id text PRIMARY KEY,
    paper_id text NOT NULL,
    source_kind text NOT NULL,
    source_uri text,
    content_hash text,
    parser text,
    parser_version text,
    is_primary boolean NOT NULL DEFAULT true,
    retrieved_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (paper_id, source_kind, source_uri)
);

CREATE INDEX IF NOT EXISTS paper_sources_paper_idx
    ON paper_sources (paper_id);

CREATE INDEX IF NOT EXISTS paper_sources_kind_idx
    ON paper_sources (source_kind);
