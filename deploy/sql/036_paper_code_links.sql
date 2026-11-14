CREATE TABLE IF NOT EXISTS paper_code_links (
    link_id text PRIMARY KEY,
    paper_id text NOT NULL,
    url text NOT NULL,
    repo_type text,
    license text,
    commit_sha text,
    confidence real NOT NULL DEFAULT 0.5,
    evidence_para_id text,
    status text NOT NULL DEFAULT 'candidate',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (paper_id, url)
);

CREATE INDEX IF NOT EXISTS paper_code_links_paper_idx
    ON paper_code_links (paper_id);

CREATE INDEX IF NOT EXISTS paper_code_links_status_idx
    ON paper_code_links (status);
