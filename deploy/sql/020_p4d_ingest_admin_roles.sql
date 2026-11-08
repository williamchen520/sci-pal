-- P4d: separate ingest and admin roles from the owner connection.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scipal_ingest') THEN
        CREATE ROLE scipal_ingest NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scipal_admin') THEN
        CREATE ROLE scipal_admin NOLOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE scipal_bench TO scipal_ingest, scipal_admin;

-- Admin may act as the owner for migrations, but is not a superuser itself.
GRANT scipal TO scipal_admin WITH INHERIT TRUE, SET TRUE;

-- Ingest can read the catalog and write only main-library content.
GRANT USAGE ON SCHEMA public, catalog, library_main, library_bench TO scipal_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA public, catalog, library_main, library_bench TO scipal_ingest;

GRANT INSERT, UPDATE, DELETE ON
    public.papers,
    public.sections,
    public.paragraphs,
    public.sentences,
    public.citations,
    public.figures,
    public."tables",
    public.sentence_links,
    public.paragraph_embeddings,
    public.paper_flags,
    public.paper_links,
    public.paper_index
TO scipal_ingest;

GRANT INSERT, UPDATE, DELETE ON
    catalog.works,
    library_main.documents,
    library_main.paper_documents,
    library_main.source_nodes
TO scipal_ingest;

COMMIT;
