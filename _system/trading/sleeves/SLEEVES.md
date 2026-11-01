# Sleeve split

Same account from `IBKR_ACCOUNT`. IB will not isolate capital. Classification is the source of truth.

## Michael (long-term residual)

Include:

- Residual stocks and unlevered funds after the exclusions below.
- Pre-`ETF_LS` baseline names.
- Strategy blacklist underlyings: JPM, BRK-B, AXP, APLD, SMR, CBRS.
- Expanded blacklist families (APLZ/APLX for APLD, SMZ for SMR, BRKC/BRKU for BRK-B, …). ls-algo never trades these; Michael trades them by hand, including LETF wrappers.

Exclude:

- SPX 0DTE: `secType=OPT` with symbol/tradingClass SPX or SPXW.
- etf-0dte (spx-0dte's SPY / QQQ 0DTE executors, clients 50/51, watchdogs 130/131). No book owns any of these, and nothing here sizes, sleeve-tags or tickets against them:
  - `etf_0dte`: any order stamped `SPY0DTE|` / `QQQ0DTE|`, and any ref-less SPY / QQQ option (positions carry no ref, so the root decides; not narrowed by expiry, because no other book held SPY or QQQ options on 2026-10-27).
  - `etf_0dte_delivery`: SPY / QQQ shares that spx-0dte's delivery forecast predicted (`<live_dir>/<spy|qqq>/<session>/expected_delivery_<account>.json`, `etf_0dte.live_dir` in `config.yaml` or `ETF_0DTE_LIVE_DIR`), and the stamped 09:30 unwind order.
  - `etf_0dte_delivery_unattributed`: SPY / QQQ shares beyond every other book's known holding that no forecast explains.
  - Shares another book is known to hold (`etf_0dte.known_share_holdings`; in the hub ledger, explicit Drew/Michael lots) keep their current bucket. None exist today: ls-algo blacklisted SPY and QQQ on 2026-09-10, so their place in the 2026-08-13 universe snapshot is membership, not a holding.
  - These rules run after the XSP and SPX rules and before the LS overlay, LS universe and owner rules; the `SPY0DTE|` / `QQQ0DTE|` stamp runs before everything.
- Systematic LETF book: `orderRef` prefix `ETF_LS|` or `B5P|`, or membership in `data/etf_ls_universe.json` / current plan export, **unless** the ticker is in the blacklist family.

Cash and T-bill ETFs (BIL, SGOV, …) count in NAV as cash, not as idea rows.

## Drew

Empty until new fills tagged `DREW_SLEEVE`. Starts at $100k plus extra margin. Does not inherit Michael's residual names.

## Snapshot files (do not import ls-algo at runtime)

- `data/blacklist.json`
- `data/etf_to_under.json`
- `data/etf_ls_universe.json`

Refresh those JSON files when the ls-algo screener universe or blacklist changes.
