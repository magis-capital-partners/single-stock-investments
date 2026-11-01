-- Bounded validated pages keep a four-year history within D1's daily write quota.
-- Older row-based generations remain readable until their normal retention.
CREATE TABLE IF NOT EXISTS sleeve_realized_pages (
 content_sha TEXT PRIMARY KEY, row_count INTEGER NOT NULL, owner_mask INTEGER NOT NULL,
 trade_min TEXT NOT NULL, trade_max TEXT NOT NULL,
 settle_min TEXT NOT NULL, settle_max TEXT NOT NULL,
 records_json TEXT NOT NULL, daily_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_realized_batch_content ON sleeve_realized_batches(content_sha);
