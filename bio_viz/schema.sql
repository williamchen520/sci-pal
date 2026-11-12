CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS code_rag;

CREATE TABLE IF NOT EXISTS code_rag.recipes (
  recipe_id text PRIMARY KEY,
  title text NOT NULL,
  chart_type text NOT NULL,
  intent text NOT NULL DEFAULT '',
  data_schema text NOT NULL DEFAULT '',
  code text NOT NULL,
  packages jsonb NOT NULL DEFAULT '[]'::jsonb,
  style_id text NOT NULL DEFAULT '',
  source text NOT NULL DEFAULT '',
  license text NOT NULL DEFAULT '',
  tested boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_rag.styles (
  style_id text PRIMARY KEY,
  name text NOT NULL,
  spec jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS code_rag.packages (
  package text NOT NULL,
  version_range text NOT NULL DEFAULT '',
  notes text NOT NULL DEFAULT '',
  PRIMARY KEY (package, version_range)
);

CREATE TABLE IF NOT EXISTS code_rag.embeddings (
  recipe_id text PRIMARY KEY REFERENCES code_rag.recipes(recipe_id) ON DELETE CASCADE,
  embedding vector(512) NOT NULL,
  model text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS code_rag.ingest_runs (
  run_id bigserial PRIMARY KEY,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  recipes integer NOT NULL DEFAULT 0,
  model text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'running'
);

CREATE INDEX IF NOT EXISTS recipes_trgm ON code_rag.recipes
  USING GIN (title gin_trgm_ops, intent gin_trgm_ops);
CREATE INDEX IF NOT EXISTS code_embeddings_hnsw ON code_rag.embeddings
  USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
