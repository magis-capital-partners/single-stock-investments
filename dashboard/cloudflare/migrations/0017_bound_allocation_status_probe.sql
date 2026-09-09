-- The allocation-status probe read millions of rows to answer a yes/no question.
--
-- loadPortfolio() asks one thing here: does the newest allocation projection for
-- this broker snapshot have any allocations behind it? The statement expressed
-- that as COUNT(a.allocation_id) over
--
--   portfolio_allocation_projections p LEFT JOIN portfolio_allocations a
--     ON a.account_alias = p.account_alias
--
-- and account_alias is the only column those two tables share -- portfolio_allocations
-- carries no source_run_id and no projection_id -- so the join is a cross product:
-- every projection row for the account paired with every allocation row, aggregated,
-- and only then cut to a single row by LIMIT 1. D1 bills rows scanned, so the LIMIT
-- bounded what came back and nothing about what was read.
--
-- Both sides grow. The publisher re-posts the same frozen snapshot on a timer and
-- every post inserts a new projection row under the same source_run_id, so the left
-- side gains a row an hour and is never pruned (retention drops projections with
-- their source run, and this run is the newest complete one, so it never leaves).
-- The right side grows with every allocation ever written.
--
-- Measured on 2026-09-09 via d1QueriesAdaptiveGroups: 3,458,448 rows read per call,
-- 27,667,584 across eight calls, against a free-tier allowance of 5,000,000 rows a
-- day. Two page loads of the portfolio view were enough to exhaust the account for
-- the rest of the UTC day, which is why the failure looked like a steady drain with
-- no single culprit in the deploy logs -- the deploys were innocent and succeeded.
--
-- _lib/portfolio.js now asks with EXISTS. These indexes make what remains two seeks:
-- the first turns ORDER BY as_of DESC LIMIT 1 into a one-row backwards walk instead
-- of a sort over every projection for the run; the second lets EXISTS stop on its
-- first hit instead of scanning portfolio_allocations when the account has none.

CREATE INDEX IF NOT EXISTS idx_portfolio_projections_account_run
  ON portfolio_allocation_projections(account_alias, source_run_id, as_of DESC);

CREATE INDEX IF NOT EXISTS idx_portfolio_allocations_account
  ON portfolio_allocations(account_alias);
