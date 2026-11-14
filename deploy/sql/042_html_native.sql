CREATE TABLE IF NOT EXISTS html_articles (
    source_id text PRIMARY KEY,
    paper_id text NOT NULL,
    source_url text,
    content_hash text,
    title text,
    doi text,
    journal text,
    published text,
    license text,
    native_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS html_sections (
    source_id text NOT NULL,
    native_section_id text NOT NULL,
    title text,
    section_order integer NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, native_section_id)
);

CREATE TABLE IF NOT EXISTS html_paragraphs (
    source_id text NOT NULL,
    native_para_id text NOT NULL,
    section_id text NOT NULL,
    text text NOT NULL,
    para_order integer NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, native_para_id)
);

CREATE INDEX IF NOT EXISTS html_articles_paper_idx ON html_articles (paper_id);
CREATE INDEX IF NOT EXISTS html_sections_source_idx ON html_sections (source_id);
CREATE INDEX IF NOT EXISTS html_paragraphs_source_idx ON html_paragraphs (source_id);
