CREATE TABLE IF NOT EXISTS jats_articles (
    source_id text PRIMARY KEY,
    paper_id text NOT NULL,
    article_type text,
    journal_title text,
    article_title text,
    license text,
    native_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jats_sections (
    source_id text NOT NULL,
    native_section_id text NOT NULL,
    sec_type text,
    title text,
    depth integer NOT NULL DEFAULT 1,
    section_path text,
    section_order integer NOT NULL DEFAULT 0,
    PRIMARY KEY (source_id, native_section_id)
);

CREATE INDEX IF NOT EXISTS jats_articles_paper_idx ON jats_articles (paper_id);
CREATE INDEX IF NOT EXISTS jats_sections_source_idx ON jats_sections (source_id);
CREATE INDEX IF NOT EXISTS jats_sections_type_idx ON jats_sections (sec_type);
