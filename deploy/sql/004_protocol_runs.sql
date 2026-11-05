CREATE TABLE IF NOT EXISTS protocol_runs (
  run_id text PRIMARY KEY,
  protocol_id text NOT NULL,
  title text,
  operator text,
  run_date text,
  status text NOT NULL DEFAULT 'planned',
  result text,
  notes text,
  done_steps text DEFAULT '[]',
  created_at text NOT NULL,
  updated_at text NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_protocol_runs_protocol ON protocol_runs(protocol_id, run_date DESC);
