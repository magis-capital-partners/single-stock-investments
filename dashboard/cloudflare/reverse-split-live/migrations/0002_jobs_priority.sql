CREATE INDEX IF NOT EXISTS rs_jobs_priority ON rs_jobs(state,priority DESC,json_extract(payload,'$.published_at') DESC,created_at);
CREATE TABLE IF NOT EXISTS rs_source_gaps (id TEXT PRIMARY KEY,source_id TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,created_at TEXT NOT NULL,resolved_at TEXT);
CREATE INDEX IF NOT EXISTS rs_source_gaps_open ON rs_source_gaps(source_id,resolved_at);
