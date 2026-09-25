-- Deploy bookkeeping for the free-tier D1 budget, and the two child-key
-- indexes the incremental dashboard seed needs to delete rows by key.
--
-- ops_state holds a handful of small rows written by the deploy itself:
--   seed:state:NNN      per-ticker content hashes of the last applied seed
--                       (written inside the seed file, so it is atomic with
--                       the rows it describes)
--   sleeve:sql_sha256   hash of the last applied Drew sleeve book
--   prune:last_date     UTC date of the last completed retention pass
-- WITHOUT ROWID: the text primary key is the table, so each write is one row
-- instead of a row plus an autoindex entry.
CREATE TABLE IF NOT EXISTS ops_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
) WITHOUT ROWID;

-- Deleting a source_documents row makes SQLite look for facts that still
-- reference it (facts.source_document_id REFERENCES source_documents). With no
-- index on the child key, every deleted document scanned the whole facts
-- table; the deploys that followed a Power Zone commit read ~90k rows that way.
CREATE INDEX IF NOT EXISTS idx_facts_source_document
  ON facts(source_document_id);

-- Same rule for evidence_tasks -> task_attempts(ticker, task_id) ON DELETE
-- CASCADE: the cascade must find the child rows by index, not by scan.
CREATE INDEX IF NOT EXISTS idx_task_attempts_task
  ON task_attempts(ticker, task_id);
