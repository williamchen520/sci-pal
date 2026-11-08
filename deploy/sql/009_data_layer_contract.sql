-- P0 data-layer contract: catalog + work + document + source node.
-- Additive only. No existing public table is modified.
-- Rollback: DROP SCHEMA library_main CASCADE; DROP SCHEMA catalog CASCADE;

BEGIN;

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS library_main;

CREATE TABLE IF NOT EXISTS catalog.libraries (
    library_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    scope               TEXT NOT NULL CHECK (scope IN ('main', 'tenant', 'benchmark')),
    owner_workspace_id  TEXT,
    source_type         TEXT NOT NULL DEFAULT 'mixed'
                        CHECK (source_type IN ('pdf', 'xml', 'md', 'mixed')),
    schema_name         TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'archived', 'building')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog.works (
    work_id             TEXT PRIMARY KEY,
    primary_doi         TEXT,
    pmid                TEXT,
    pmcid               TEXT,
    title               TEXT,
    year                INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_works_doi
    ON catalog.works (lower(primary_doi))
    WHERE primary_doi IS NOT NULL AND primary_doi <> '';

CREATE INDEX IF NOT EXISTS idx_works_pmid
    ON catalog.works (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_works_pmcid
    ON catalog.works (pmcid) WHERE pmcid IS NOT NULL;

CREATE TABLE IF NOT EXISTS library_main.documents (
    document_id         TEXT PRIMARY KEY,
    work_id             TEXT NOT NULL REFERENCES catalog.works(work_id) ON DELETE CASCADE,
    library_id          TEXT NOT NULL REFERENCES catalog.libraries(library_id) ON DELETE CASCADE,
    source_type         TEXT NOT NULL CHECK (source_type IN ('pdf', 'xml', 'md')),
    source_path         TEXT,
    sha256              TEXT NOT NULL,
    parser              TEXT,
    parser_version      TEXT,
    imported_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (work_id, source_type, sha256)
);

CREATE INDEX IF NOT EXISTS idx_documents_library
    ON library_main.documents (library_id);
CREATE INDEX IF NOT EXISTS idx_documents_work
    ON library_main.documents (work_id);
CREATE INDEX IF NOT EXISTS idx_documents_sha
    ON library_main.documents (sha256);

CREATE TABLE IF NOT EXISTS library_main.source_nodes (
    node_id             TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL REFERENCES library_main.documents(document_id) ON DELETE CASCADE,
    parent_node_id      TEXT REFERENCES library_main.source_nodes(node_id) ON DELETE CASCADE,
    node_type           TEXT NOT NULL,
    source_path         TEXT,
    source_order        INTEGER,
    native_json         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_nodes_document
    ON library_main.source_nodes (document_id);
CREATE INDEX IF NOT EXISTS idx_source_nodes_parent
    ON library_main.source_nodes (parent_node_id);
CREATE INDEX IF NOT EXISTS idx_source_nodes_type
    ON library_main.source_nodes (node_type);

INSERT INTO catalog.libraries
    (library_id, name, scope, owner_workspace_id, source_type, schema_name, status)
VALUES
    ('library_main', 'SciPal main library', 'main', NULL, 'mixed', 'library_main', 'active')
ON CONFLICT (library_id) DO NOTHING;

COMMIT;
