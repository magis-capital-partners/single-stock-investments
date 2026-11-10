CREATE TABLE IF NOT EXISTS rs_announcement_watches(event_id TEXT PRIMARY KEY,ticker TEXT,first_seen_at TEXT NOT NULL,registered_at TEXT NOT NULL,watch_until TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rs_announcement_quote_samples(id TEXT PRIMARY KEY,ticker TEXT NOT NULL,observed_at TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rs_announcement_quote_clock ON rs_announcement_quote_samples(observed_at,id);
CREATE TABLE IF NOT EXISTS rs_announcement_quote_archives(id TEXT PRIMARY KEY,recorded_at TEXT NOT NULL,payload TEXT NOT NULL);
