-- P3b: independent benchmark library.

BEGIN;

CREATE SCHEMA IF NOT EXISTS library_bench;

CREATE TABLE IF NOT EXISTS library_bench.documents (
    document_id     TEXT PRIMARY KEY,
    work_id         TEXT NOT NULL REFERENCES catalog.works(work_id) ON DELETE CASCADE,
    library_id      TEXT NOT NULL REFERENCES catalog.libraries(library_id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL CHECK (source_type IN ('pdf', 'xml', 'md')),
    source_path     TEXT,
    sha256          TEXT NOT NULL,
    parser          TEXT,
    parser_version  TEXT,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (work_id, source_type, sha256)
);

CREATE TABLE IF NOT EXISTS library_bench.source_nodes (
    node_id         TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES library_bench.documents(document_id) ON DELETE CASCADE,
    parent_node_id  TEXT REFERENCES library_bench.source_nodes(node_id) ON DELETE CASCADE,
    node_type       TEXT NOT NULL,
    source_path     TEXT,
    source_order    INTEGER,
    native_json     JSONB
);

CREATE TABLE IF NOT EXISTS library_bench.sections (
    section_id      TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES library_bench.documents(document_id) ON DELETE CASCADE,
    parent_id       TEXT REFERENCES library_bench.sections(section_id) ON DELETE CASCADE,
    level           INTEGER,
    seq             INTEGER,
    title           TEXT,
    path            TEXT,
    depth           INTEGER,
    source_node_id  TEXT REFERENCES library_bench.source_nodes(node_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS library_bench.paragraphs (
    para_id         TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES library_bench.documents(document_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES library_bench.sections(section_id) ON DELETE SET NULL,
    seq             INTEGER,
    text            TEXT,
    source_node_id  TEXT REFERENCES library_bench.source_nodes(node_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS library_bench.sentences (
    sentence_id     TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES library_bench.documents(document_id) ON DELETE CASCADE,
    para_id         TEXT NOT NULL REFERENCES library_bench.paragraphs(para_id) ON DELETE CASCADE,
    section_id      TEXT REFERENCES library_bench.sections(section_id) ON DELETE SET NULL,
    seq             INTEGER,
    text            TEXT,
    char_start      INTEGER,
    char_end        INTEGER,
    source_node_id  TEXT REFERENCES library_bench.source_nodes(node_id) ON DELETE SET NULL,
    search_vector   TSVECTOR
);

CREATE INDEX IF NOT EXISTS idx_bench_documents_work ON library_bench.documents (work_id);
CREATE INDEX IF NOT EXISTS idx_bench_documents_sha ON library_bench.documents (sha256);
CREATE INDEX IF NOT EXISTS idx_bench_nodes_document ON library_bench.source_nodes (document_id);
CREATE INDEX IF NOT EXISTS idx_bench_nodes_parent ON library_bench.source_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_bench_sections_document ON library_bench.sections (document_id);
CREATE INDEX IF NOT EXISTS idx_bench_paragraphs_document ON library_bench.paragraphs (document_id);
CREATE INDEX IF NOT EXISTS idx_bench_paragraphs_section ON library_bench.paragraphs (section_id);
CREATE INDEX IF NOT EXISTS idx_bench_sentences_document ON library_bench.sentences (document_id);
CREATE INDEX IF NOT EXISTS idx_bench_sentences_para ON library_bench.sentences (para_id);
CREATE INDEX IF NOT EXISTS idx_bench_sentences_search ON library_bench.sentences USING gin (search_vector);

INSERT INTO catalog.libraries
    (library_id, name, scope, owner_workspace_id, source_type, schema_name, status)
VALUES
    ('library_bench', 'P3b PMC OA benchmark', 'benchmark', NULL, 'xml', 'library_bench', 'active')
ON CONFLICT (library_id) DO NOTHING;

COMMIT;
