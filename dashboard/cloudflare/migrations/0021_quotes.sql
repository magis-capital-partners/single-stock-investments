-- Latest-quote snapshots for the dashboard's live quote strip.
--
-- One row per symbol, replaced on each ingest: the dashboard only ever asks
-- "what is the last price and how old is it", never for history (history
-- stays in the committed market-data files). The Cloudflare cron worker
-- (dashboard/cloudflare/quotes-ingest-worker.js) refreshes these from a
-- public quote source; nothing here reads a brokerage session.
--
-- as_of is the source's quote time, not the ingest time, so the API can
-- report staleness honestly when a feed stalls.

CREATE TABLE IF NOT EXISTS quotes (
  symbol TEXT PRIMARY KEY,
  price REAL,
  previous_close REAL,
  as_of TEXT NOT NULL,
  source TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quotes_as_of ON quotes(as_of DESC);
