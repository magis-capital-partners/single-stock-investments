-- Let /api/v1/market-risk/alerts walk an index instead of scanning every alert.
--
-- The route orders alerts by severity rank, then recency:
--
--   ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
--                          WHEN 'medium' THEN 2 ELSE 3 END, updated_at DESC
--   LIMIT ?
--
-- No index could produce that order, so every call read the whole table, sorted
-- it, and kept 100 rows -- and the SPA calls it (and /health, which counted the
-- same table) on every page load. D1 bills rows read, so LIMIT bounded the
-- response and nothing else, on a table retention never pruned.
--
-- These are indexes on the exact rank expression the route uses (SQLite only
-- matches an expression index when the query's expression is the same tree), so
-- the planner can read the first LIMIT entries in order and stop:
--
--   * idx_market_risk_alerts_rank serves ?open=false (all alerts): an ordered
--     index scan that stops after LIMIT entries;
--   * idx_market_risk_alerts_open_rank leads with closed_at, so the default
--     open-only view seeks `closed_at IS NULL` and reads its rows already in
--     rank order -- no sort pass, stops at LIMIT -- and /health counts open
--     alerts as a covering seek that never touches closed ones.
--
-- The open index is deliberately not partial. With the older
-- idx_market_risk_alerts_open(closed_at, severity, updated_at) also present, the
-- planner preferred that seek plus a sort over a partial index; leading with
-- closed_at gives it the same seek with the order already satisfied, which it
-- takes with or without ANALYZE statistics. The older index stays: a
-- closed_at-range retention delete can use it.
--
-- The route's SQL works with or without these indexes -- it is only the row
-- count that changes -- so a deploy that ships the code before this migration
-- lands (a quota-deferred migration stage) degrades to the old cost, not to an
-- error.
--
-- This migration adds indexes only. It does not bound the table: retention for
-- market_risk_alerts belongs to the deploy-time retention script
-- (_system/scripts/prune_cloudflare_d1.py) and is changed separately from this
-- file. Nothing here depends on that change or on any other migration landing
-- first.

CREATE INDEX IF NOT EXISTS idx_market_risk_alerts_rank
  ON market_risk_alerts(
    (CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END),
    updated_at DESC
  );

CREATE INDEX IF NOT EXISTS idx_market_risk_alerts_open_rank
  ON market_risk_alerts(
    closed_at,
    (CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END),
    updated_at DESC
  );
