-- Client ingest tracking plugin (disabled by default)
CREATE TABLE IF NOT EXISTS ingest_tracking_batches (
    batch_id     text PRIMARY KEY,
    source       text NOT NULL DEFAULT '',
    status       text NOT NULL DEFAULT 'running',
    total        integer NOT NULL DEFAULT 0,
    clean        integer NOT NULL DEFAULT 0,
    warning      integer NOT NULL DEFAULT 0,
    needs_review integer NOT NULL DEFAULT 0,
    duplicate    integer NOT NULL DEFAULT 0,
    rejected     integer NOT NULL DEFAULT 0,
    meta         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);

CREATE TABLE IF NOT EXISTS ingest_tracking_items (
    id             bigserial PRIMARY KEY,
    batch_id       text NOT NULL REFERENCES ingest_tracking_batches(batch_id) ON DELETE CASCADE,
    filename       text NOT NULL DEFAULT '',
    paper_id       text,
    quality_status text NOT NULL DEFAULT 'clean',
    flags          jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest_tracking_findings (
    id          bigserial PRIMARY KEY,
    batch_id    text NOT NULL REFERENCES ingest_tracking_batches(batch_id) ON DELETE CASCADE,
    item_id     bigint REFERENCES ingest_tracking_items(id) ON DELETE CASCADE,
    code        text NOT NULL,
    severity    text NOT NULL,
    message     text NOT NULL DEFAULT '',
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    resolved_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ingest_tracking_items_batch
    ON ingest_tracking_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_ingest_tracking_items_paper
    ON ingest_tracking_items(paper_id);
CREATE INDEX IF NOT EXISTS idx_ingest_tracking_findings_batch
    ON ingest_tracking_findings(batch_id);

ALTER TABLE papers ADD COLUMN IF NOT EXISTS quality_status text NOT NULL DEFAULT 'clean';
ALTER TABLE papers ADD COLUMN IF NOT EXISTS quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS quality_checked_at timestamptz;
CREATE INDEX IF NOT EXISTS idx_papers_quality_status ON papers(quality_status);
