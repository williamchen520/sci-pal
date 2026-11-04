CREATE TABLE IF NOT EXISTS notes (
  note_id text PRIMARY KEY,
  user_id text NOT NULL,
  workspace_id text NOT NULL DEFAULT 'ws_default',
  paper_id text,
  para_id text,
  content text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_notes_workspace_user ON notes(workspace_id, user_id);
CREATE INDEX IF NOT EXISTS idx_notes_paper ON notes(paper_id);
