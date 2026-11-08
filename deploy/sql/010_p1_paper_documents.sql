-- P1 bridge: legacy paper_id -> work-level document_id.
-- Additive only.

BEGIN;

CREATE TABLE IF NOT EXISTS library_main.paper_documents (
    paper_id        TEXT PRIMARY KEY REFERENCES public.papers(paper_id) ON DELETE CASCADE,
    document_id     TEXT NOT NULL REFERENCES library_main.documents(document_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_paper_documents_document
    ON library_main.paper_documents (document_id);

COMMIT;
