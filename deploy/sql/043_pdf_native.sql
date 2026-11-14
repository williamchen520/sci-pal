CREATE TABLE IF NOT EXISTS pdf_documents (
    source_id text PRIMARY KEY,
    paper_id text NOT NULL,
    source_uri text,
    content_hash text,
    parser text,
    page_count integer NOT NULL DEFAULT 0,
    native_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pdf_paragraphs (
    source_id text NOT NULL,
    native_para_id text NOT NULL,
    para_id text NOT NULL,
    page integer,
    bbox text,
    text text NOT NULL,
    para_order integer NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, native_para_id)
);

CREATE INDEX IF NOT EXISTS pdf_documents_paper_idx ON pdf_documents (paper_id);
CREATE INDEX IF NOT EXISTS pdf_paragraphs_source_idx ON pdf_paragraphs (source_id);
