# Historical evidence required for account results

The v3 publication retires the former bar/proxy P&L. Historical account performance remains unavailable when any selected entry or subsequent position path is unsupported. A missing observation is neither zero P&L nor a failed execution. This is an evidence repair, not a claim that previously missing historical records have been obtained.

## Observed inputs and diagnostics

- The local archive holds observed one-second venue bars and, for some sessions, sampled venue quotes. It contains neither qualified national quotes nor historical usable borrow approvals.
- `normalize-free` rebuilds from existing hash-verified download receipts only. It makes no network request. Uncaptured successor symbols and off-venue securities receive explicit source gaps; they are not empty observed sessions.
- `security_lifecycle.v1.json` binds dated corrections to issuer and primary filings. TNFA continues into QCLS with the same security. DBGI's OTC interval and Nasdaq return are separate venue states. PIXY's suspension does not release a short liability.
- The price-only benchmark requires original-date official opening and horizon-date official closing auctions plus a nonconflicting split factor. Missing official prices remain missing, even if a venue last-trade price or a later filing's price is available. The mean among complete price pairs has selection bias and excludes costs/access.
- Independent entry diagnostics require fresh observed quotes, entire-bar clearance after acknowledgement and valid order limits. Their 50% capture parameter is an uncalibrated scenario; it establishes no observed fill or completed cover. They cannot be added into an account return.

## Qualified execution and financing

Qualified event sessions use the existing [execution data contract](../ssr_execution_v1/DATA_CONTRACT.md), including national quotes, eligible trades, book/queue history, identity, source clocks, dated grids and routes. Verified mode additionally requires archived borrow quantity/rate/expiry and attestations for dated margin, loan recall terms and corporate-action settlement. Bar-only input cannot satisfy that contract.

Optional `historical_costs.local.json` stays inside the ignored local `ssr_execution_v2` cache. Its schema is `third_plus_historical_costs.v1`, with `borrow_terms` and `margin_terms` arrays. Each record requires issuer, ticker, inclusive ISO `from`/`to` dates, `available_at`, `source_file` relative to that cache, and `source_sha256`. Borrow rows include nonnegative annual `apr`; margin rows include nonnegative `fraction` and `minimum_per_share`. The source file is read and hash-checked, must stay inside the cache, and cannot refer to sealed/holdout data. Only one unambiguous row already available by that session's 09:31 ET can apply. Missing records, future clocks and conflicting intervals fail closed. Nothing queries IB or ThetaData.

Historical loan access and actual broker settlements require their own records; an indicative present-day rate is not a historical locate. Fixed 50%/150% APR values remain explicit optional scenario settings in low-level research fixtures, never historical observations in the published account.

## Account timing and accounting

Morning equity and pending parent reservations determine admission. The later outcome of a no-fill cannot free an earlier morning slot; future entry proceeds and closing marks cannot increase another parent's morning budget. Explicit hypothetical budgets are 0.25% equity per issuer, 1% sleeve gross, 2% loss under a +200% squeeze, and 80% margin usage, with three issuer slots. These limits are not evidence of the historical broker's margin policy.

Both sides respect resting limits. Unknown cover data stop the account path and withhold full-period returns and drawdown. No frozen-mark continuation manufactures years of borrow charges or blocks later slots as if a data gap were a real uncloseable position. A split-adjusted whole-share overbuy pays its full cash cost and retains the surplus as a marked long asset. It is not a zero-value asset or an invented broker cash-in-lieu settlement.

The 21 signals and 24 settings remain retrospective. Unit tests establish mechanical invariants, not profitability. No ThetaData, Gateway, broker socket, paid download or sealed holdout is part of this repair.
