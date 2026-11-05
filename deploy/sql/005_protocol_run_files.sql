CREATE TABLE IF NOT EXISTS protocol_run_files (
  file_id text PRIMARY KEY,
  run_id text NOT NULL,
  filename text,
  stored_name text NOT NULL,
  content_type text,
  size bigint,
  uploaded_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_protocol_run_files_run ON protocol_run_files(run_id, uploaded_at);
