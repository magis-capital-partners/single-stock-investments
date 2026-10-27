-- Realized history is independent of ephemeral portfolio snapshots/retention.
CREATE TABLE IF NOT EXISTS sleeve_realized_generations (
 generation_id TEXT PRIMARY KEY, account TEXT NOT NULL, through_date TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('staging','complete')), manifest_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_realized_generation_account ON sleeve_realized_generations(account,through_date);
CREATE TABLE IF NOT EXISTS sleeve_realized_batches (
 generation_id TEXT NOT NULL, batch_index INTEGER NOT NULL, content_sha TEXT NOT NULL,
 row_count INTEGER NOT NULL, PRIMARY KEY(generation_id,batch_index));
CREATE TABLE IF NOT EXISTS sleeve_realized_records (
 generation_id TEXT NOT NULL, record_id TEXT NOT NULL, owner TEXT NOT NULL,
 trade_date TEXT NOT NULL, settlement_date TEXT, settlement_status TEXT NOT NULL,
 ticker TEXT NOT NULL, payload_json TEXT NOT NULL, PRIMARY KEY(generation_id,record_id));
CREATE INDEX IF NOT EXISTS idx_realized_owner_trade ON sleeve_realized_records(generation_id,owner,trade_date,record_id);
CREATE INDEX IF NOT EXISTS idx_realized_owner_settle ON sleeve_realized_records(generation_id,owner,settlement_date,record_id);
CREATE INDEX IF NOT EXISTS idx_realized_ticker_trade ON sleeve_realized_records(generation_id,owner,ticker,trade_date,record_id);
CREATE TABLE IF NOT EXISTS sleeve_realized_daily (
 generation_id TEXT NOT NULL, owner TEXT NOT NULL, trade_date TEXT NOT NULL,
 settlement_date TEXT NOT NULL, settlement_status TEXT NOT NULL, ticker TEXT NOT NULL,
 payload_json TEXT NOT NULL, batch_index INTEGER NOT NULL,
 PRIMARY KEY(generation_id,batch_index,owner,trade_date,settlement_date,settlement_status,ticker));
CREATE INDEX IF NOT EXISTS idx_realized_daily_trade ON sleeve_realized_daily(generation_id,owner,trade_date);
CREATE INDEX IF NOT EXISTS idx_realized_daily_settle ON sleeve_realized_daily(generation_id,owner,settlement_date);
CREATE TABLE IF NOT EXISTS sleeve_realized_current (
 account TEXT PRIMARY KEY, generation_id TEXT NOT NULL, through_date TEXT NOT NULL,
 published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 prepared_at TEXT NOT NULL DEFAULT '', source_generated TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sleeve_realized_archive_parts (
 account TEXT NOT NULL, report_id TEXT NOT NULL, part INTEGER NOT NULL,
 content_sha TEXT NOT NULL, size INTEGER NOT NULL,
 PRIMARY KEY(account,report_id,part));
