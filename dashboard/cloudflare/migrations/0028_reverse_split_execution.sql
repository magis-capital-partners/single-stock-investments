-- Private, paper-only journal projections. Retrying a snapshot does not create another trade.
CREATE TABLE IF NOT EXISTS rs_execution_paper (
  session_id TEXT PRIMARY KEY,
  observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  ended INTEGER NOT NULL CHECK (ended IN (0, 1)),
  body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rs_execution_paper_latest
  ON rs_execution_paper(observed_at DESC, session_id DESC);
