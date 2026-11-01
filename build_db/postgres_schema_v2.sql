-- SciPal schema v2: source-aware structure
-- P1: empty schema only; no data migration.
-- XML keeps source_nodes/XPath; PDF keeps pages/blocks/bbox; figures/tables bind to sections.

CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    workspace_id    TEXT NOT NULL DEFAULT 'ws_default',
    title           TEXT,
    authors         TEXT,
    journal         TEXT,
    year            INTEGER,
    doi             TEXT,
    abstract        TEXT,
    parse_status    TEXT,
    source_flags    JSONB NOT NULL DEFAULT '{}'::jsonb,
    fulltext_status TEXT NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    source_path     TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    parser          TEXT NOT NULL,
    parser_version  TEXT,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (paper_id, source_type, sha256)
);

CREATE TABLE IF NOT EXISTS source_nodes (
    node_id         TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    parent_node_id  TEXT REFERENCES source_nodes(node_id),
    node_type       TEXT NOT NULL,
    source_path     TEXT,
    source_order    INTEGER,
    native_json     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_nodes_paper ON source_nodes(paper_id);
CREATE INDEX IF NOT EXISTS idx_source_nodes_parent ON source_nodes(parent_node_id);
CREATE INDEX IF NOT EXISTS idx_source_nodes_document ON source_nodes(document_id);

CREATE TABLE IF NOT EXISTS sections (
    section_id      TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    parent_id       TEXT REFERENCES sections(section_id),
    level           INTEGER NOT NULL,
    seq             INTEGER NOT NULL,
    title           TEXT,
    path            TEXT,
    depth           INTEGER,
    source_node_id  TEXT REFERENCES source_nodes(node_id) DEFERRABLE INITIALLY DEFERRED,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    page            INTEGER,
    bbox            TEXT,
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf', 'xml-unavailable', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS idx_sections_paper ON sections(paper_id, seq);
CREATE INDEX IF NOT EXISTS idx_sections_parent ON sections(parent_id);
CREATE INDEX IF NOT EXISTS idx_sections_source_node ON sections(source_node_id);

CREATE TABLE IF NOT EXISTS paragraphs (
    para_id         TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES sections(section_id),
    seq             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    source_node_id  TEXT REFERENCES source_nodes(node_id) DEFERRABLE INITIALLY DEFERRED,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    page            INTEGER,
    bbox            TEXT,
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf', 'xml-unavailable', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS idx_paragraphs_paper ON paragraphs(paper_id, seq);
CREATE INDEX IF NOT EXISTS idx_paragraphs_section ON paragraphs(section_id, seq);
CREATE INDEX IF NOT EXISTS idx_paragraphs_source_node ON paragraphs(source_node_id);

CREATE TABLE IF NOT EXISTS sentences (
    sentence_id     TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    para_id         TEXT NOT NULL REFERENCES paragraphs(para_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES sections(section_id),
    seq             INTEGER NOT NULL,
    text            TEXT NOT NULL,
    char_start      INTEGER,
    char_end        INTEGER,
    source_node_id  TEXT REFERENCES source_nodes(node_id) DEFERRABLE INITIALLY DEFERRED,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    page            INTEGER,
    bbox            TEXT,
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf', 'xml-unavailable', 'unavailable')),
    search_vector   tsvector GENERATED ALWAYS AS
        (to_tsvector('english', coalesce(text, ''))) STORED
);

CREATE INDEX IF NOT EXISTS idx_sentences_paper ON sentences(paper_id);
CREATE INDEX IF NOT EXISTS idx_sentences_para ON sentences(para_id, seq);
CREATE INDEX IF NOT EXISTS idx_sentences_section ON sentences(section_id);
CREATE INDEX IF NOT EXISTS idx_sentences_source_node ON sentences(source_node_id);
CREATE INDEX IF NOT EXISTS idx_sentences_search ON sentences USING GIN (search_vector);

CREATE TABLE IF NOT EXISTS figures (
    fig_id          TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES sections(section_id),
    para_id         TEXT REFERENCES paragraphs(para_id),
    fig_number      TEXT,
    caption         TEXT,
    file_path       TEXT,
    source_node_id  TEXT REFERENCES source_nodes(node_id) DEFERRABLE INITIALLY DEFERRED,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    page            INTEGER,
    bbox            TEXT,
    placement_source TEXT NOT NULL DEFAULT 'unresolved'
        CHECK (placement_source IN ('jats-parent', 'pdf-caption', 'pdf-region', 'unresolved')),
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf', 'xml-unavailable', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS idx_figures_paper ON figures(paper_id);
CREATE INDEX IF NOT EXISTS idx_figures_section ON figures(section_id);
CREATE INDEX IF NOT EXISTS idx_figures_para ON figures(para_id);

CREATE TABLE IF NOT EXISTS "tables" (
    table_id        TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES sections(section_id),
    para_id         TEXT REFERENCES paragraphs(para_id),
    table_number    TEXT,
    caption         TEXT,
    markdown        TEXT,
    source_node_id  TEXT REFERENCES source_nodes(node_id) DEFERRABLE INITIALLY DEFERRED,
    source_type     TEXT NOT NULL CHECK (source_type IN ('xml', 'pdf')),
    page            INTEGER,
    bbox            TEXT,
    placement_source TEXT NOT NULL DEFAULT 'unresolved'
        CHECK (placement_source IN ('jats-parent', 'pdf-caption', 'pdf-region', 'unresolved')),
    coordinate_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (coordinate_source IN ('pdf', 'xml-unavailable', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS idx_tables_paper ON "tables"(paper_id);
CREATE INDEX IF NOT EXISTS idx_tables_section ON "tables"(section_id);
CREATE INDEX IF NOT EXISTS idx_tables_para ON "tables"(para_id);

CREATE TABLE IF NOT EXISTS pdf_pages (
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    page_no         INTEGER NOT NULL,
    width           DOUBLE PRECISION,
    height          DOUBLE PRECISION,
    text            TEXT,
    layout_json     JSONB,
    PRIMARY KEY (paper_id, page_no)
);

CREATE TABLE IF NOT EXISTS pdf_blocks (
    block_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    page_no         INTEGER NOT NULL,
    bbox            TEXT NOT NULL,
    block_type      TEXT,
    text            TEXT,
    parent_block_id TEXT REFERENCES pdf_blocks(block_id),
    source_order    INTEGER,
    FOREIGN KEY (paper_id, page_no) REFERENCES pdf_pages(paper_id, page_no)
);

CREATE INDEX IF NOT EXISTS idx_pdf_blocks_page ON pdf_blocks(paper_id, page_no, source_order);
