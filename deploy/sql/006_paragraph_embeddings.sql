-- G4a: paragraph embeddings in production schema
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS paragraph_embeddings (
    para_id    text NOT NULL PRIMARY KEY,
    paper_id   text NOT NULL,
    embedding  vector(768) NOT NULL,
    model      text NOT NULL DEFAULT 'bge-base-en-v1.5',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS paragraph_embeddings_paper_idx
    ON paragraph_embeddings (paper_id);

CREATE INDEX IF NOT EXISTS paragraph_embeddings_hnsw
    ON paragraph_embeddings USING hnsw (embedding vector_cosine_ops);
