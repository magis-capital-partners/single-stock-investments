-- Isolated research data. No broker connection, order or locate acceptance.
CREATE TABLE IF NOT EXISTS rs_execution_policies(id TEXT PRIMARY KEY,registered_at TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rs_execution_tracks(id TEXT PRIMARY KEY,event_id TEXT NOT NULL,policy_id TEXT NOT NULL,ticker TEXT,state TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rs_execution_tracks_policy ON rs_execution_tracks(policy_id,state,updated_at);
CREATE INDEX IF NOT EXISTS rs_execution_tracks_event ON rs_execution_tracks(event_id,state);
CREATE TABLE IF NOT EXISTS rs_execution_records(id TEXT PRIMARY KEY,track_id TEXT NOT NULL,recorded_at TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rs_execution_records_track ON rs_execution_records(track_id,recorded_at,id);
CREATE TABLE IF NOT EXISTS rs_borrow_observations(id TEXT PRIMARY KEY,ticker TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,as_of TEXT,observed_at TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS rs_borrow_ticker_day ON rs_borrow_observations(ticker,day,observed_at,id);
CREATE INDEX IF NOT EXISTS rs_borrow_recent ON rs_borrow_observations(observed_at DESC,id);
CREATE INDEX IF NOT EXISTS rs_execution_recent ON rs_execution_tracks(updated_at DESC);
CREATE TABLE IF NOT EXISTS rs_execution_daily(id TEXT PRIMARY KEY,policy_id TEXT NOT NULL,day TEXT NOT NULL,payload TEXT NOT NULL);
