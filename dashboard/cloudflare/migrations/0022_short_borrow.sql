-- Public short-alpha indications, not account positions.
CREATE TABLE IF NOT EXISTS short_borrow_sources(
 id TEXT PRIMARY KEY,source TEXT NOT NULL,as_of TEXT NOT NULL,captured_at TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,source_rows INTEGER NOT NULL,checksum_verified INTEGER NOT NULL,
 time_basis TEXT NOT NULL,source_url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS short_borrow_observations(
 source_id TEXT NOT NULL,symbol TEXT NOT NULL,as_of TEXT NOT NULL,fee_apr REAL,rebate_apr REAL,
 available_shares INTEGER,available_at_least INTEGER NOT NULL DEFAULT 0,conid TEXT,isin TEXT,
 cusip TEXT,currency TEXT,quality TEXT NOT NULL,PRIMARY KEY(source_id,symbol));
CREATE INDEX IF NOT EXISTS idx_short_borrow_symbol_time ON short_borrow_observations(symbol,as_of DESC);
CREATE INDEX IF NOT EXISTS idx_short_borrow_source_time ON short_borrow_sources(source,as_of DESC);
CREATE TABLE IF NOT EXISTS short_borrow_current(
 symbol TEXT PRIMARY KEY,source_id TEXT NOT NULL,as_of TEXT NOT NULL,fee_apr REAL,
 available_shares INTEGER,available_at_least INTEGER NOT NULL,quality TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS short_borrow_collections(
 id TEXT PRIMARY KEY,attempted_at TEXT NOT NULL,status TEXT NOT NULL,detail TEXT,source_id TEXT);
