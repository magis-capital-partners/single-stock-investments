-- Sleeve positions carry option identity, and are keyed by contract.
--
-- Two problems with (owner, ticker) as the primary key. The classifier keys an
-- option to its UNDERLYING -- classify_positions.py returns `under or ticker`
-- for OPT/FOP -- so a call and a put on the same name are the same row, and the
-- second INSERT in the ingest batch fails the whole POST. And the page could
-- only ever print "APLD", which does not say which contract: strike, expiry and
-- right never left the Flex statement.
--
-- position_key is the contract (local_symbol, e.g. "APLD  261009C00038000") for
-- anything with one, and the ticker otherwise. `ticker` stays the underlying so
-- sleeve_notes and sleeve_ideas keep matching on it -- a thesis is about the
-- name, not about one expiry.
--
-- Rebuild rather than ALTER: SQLite cannot change a primary key in place. The
-- copy is exact, and the table is empty in production at the time of writing
-- (checked 2026-09-10), so this is a rename in all but name.

CREATE TABLE IF NOT EXISTS sleeve_positions_v2 (
  owner TEXT NOT NULL CHECK (owner IN ('drew', 'michael')),
  position_key TEXT NOT NULL,
  ticker TEXT NOT NULL,
  qty REAL NOT NULL,
  mark REAL,
  market_value REAL,
  sec_type TEXT,
  classifier_reason TEXT,
  conid INTEGER,
  local_symbol TEXT,
  expiry TEXT,
  strike REAL,
  right_code TEXT,
  multiplier REAL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (owner, position_key)
);

INSERT OR IGNORE INTO sleeve_positions_v2 (
  owner, position_key, ticker, qty, mark, market_value, sec_type, classifier_reason, synced_at
)
SELECT owner, ticker, ticker, qty, mark, market_value, sec_type, classifier_reason, synced_at
FROM sleeve_positions;

DROP TABLE sleeve_positions;

ALTER TABLE sleeve_positions_v2 RENAME TO sleeve_positions;

-- The book reads every row for one owner, and the note/idea join is by ticker.
CREATE INDEX IF NOT EXISTS idx_sleeve_positions_owner_ticker
  ON sleeve_positions(owner, ticker);
