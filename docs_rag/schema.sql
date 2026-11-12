CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS docs_rag;

CREATE TABLE IF NOT EXISTS docs_rag.documents (
  doc_id text PRIMARY KEY,
  path text NOT NULL UNIQUE,
  title text NOT NULL DEFAULT '',
  category text NOT NULL DEFAULT '',
  summary text NOT NULL DEFAULT '',
  content text NOT NULL,
  content_sha256 text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS docs_rag.chunks (
  chunk_id text PRIMARY KEY,
  doc_id text NOT NULL REFERENCES docs_rag.documents(doc_id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  heading text NOT NULL DEFAULT '',
  text text NOT NULL,
  token_count integer NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS docs_rag.embeddings (
  chunk_id text PRIMARY KEY REFERENCES docs_rag.chunks(chunk_id) ON DELETE CASCADE,
  embedding vector(512) NOT NULL,
  model text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS docs_rag.ingest_runs (
  run_id bigserial PRIMARY KEY,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  docs integer NOT NULL DEFAULT 0,
  chunks integer NOT NULL DEFAULT 0,
  model text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS chunks_fts_idx ON docs_rag.chunks
  USING GIN (to_tsvector('simple', text));
CREATE INDEX IF NOT EXISTS chunks_trgm_idx ON docs_rag.chunks
  USING GIN (text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS embeddings_hnsw ON docs_rag.embeddings
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
