CREATE TABLE IF NOT EXISTS paper_code_libraries (
    binding_id text PRIMARY KEY,
    paper_id text NOT NULL,
    link_id text NOT NULL,
    library_id text NOT NULL,
    snapshot_id text,
    status text NOT NULL DEFAULT 'bound',
    parser_supported boolean NOT NULL DEFAULT false,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (paper_id, link_id)
);

CREATE INDEX IF NOT EXISTS paper_code_libraries_paper_idx
    ON paper_code_libraries (paper_id);

CREATE INDEX IF NOT EXISTS paper_code_libraries_library_idx
    ON paper_code_libraries (library_id);
