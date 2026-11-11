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
- etf-0dte (spx-0dte's SPY / QQQ / TSLA / NVDA / AMZN 0DTE executors, clients 50-54, watchdogs 130-134). No book owns any of these, and nothing here sizes, sleeve-tags or tickets against them:
  - `etf_0dte`: any order stamped `SPY0DTE|` / `QQQ0DTE|` / `TSLA0DTE|` / `NVDA0DTE|` / `AMZN0DTE|`, and any ref-less SPY / QQQ / TSLA / NVDA / AMZN option (positions carry no ref, so the root decides; not narrowed by expiry, because no other book held SPY or QQQ options on 2026-10-27, TSLA options at the 2026-11-05 Flex, or NVDA or AMZN options at the 2026-08-28 Flex, the newest this repo has seen). Before 2026-11-10 a ref-less NVDA or AMZN option was a Drew LS overlay; an overlay stamped `ETF_LS|MANUAL|SELLPUT|` / `SELLCALL|` still is.
  - `etf_0dte_delivery`: SPY / QQQ / TSLA / NVDA / AMZN shares that spx-0dte's delivery forecast predicted (`<live_dir>/<spy|qqq|tsla|nvda|amzn>/<session>/expected_delivery_<account>.json`, `etf_0dte.live_dir` in `config.yaml` or `ETF_0DTE_LIVE_DIR`), and the stamped 09:30 unwind order.
  - `etf_0dte_delivery_unattributed`: SPY / QQQ / TSLA / NVDA / AMZN shares beyond every other book's known holding that no forecast explains.
  - Shares another book is known to hold (`etf_0dte.known_share_holdings`; in the hub ledger, explicit Drew/Michael lots) keep their current bucket. None is declared today: ls-algo blacklisted SPY and QQQ on 2026-09-10, so their place in the 2026-08-13 universe snapshot is membership, not a holding. TSLA is in that snapshot too, and ls-algo still held +11 shares at the 2026-11-05 Flex; the owner is closing them by hand, so they stay undeclared and read `etf_0dte_delivery_unattributed` until then. TSLA's wrappers (TSLL, TSLQ, TSLT, TSYY, ...) are other roots and stay in the systematic LETF book. NVDA and AMZN (added 2026-11-10) are the same case: universe underlyings that no SSI book holds (AMZN's research stance "hold" is a classification, not a position), with ls-algo holding shares of both as LETF-pair hedges at the 2026-08-28 Flex. Those stay undeclared and read `etf_0dte_delivery_unattributed` until the owner closes them. Their wrappers (NVDL, NVDU, NVDQ, NVDD, NVDS, NVDX, NVDG, NVDY, NVD, AMZU, AMZZ, AMZD, AMZY, AMZO, ...) are other roots and stay in the systematic LETF book.
  - These rules run after the XSP and SPX rules and before the LS overlay, LS universe and owner rules; the `SPY0DTE|` / `QQQ0DTE|` / `TSLA0DTE|` / `NVDA0DTE|` / `AMZN0DTE|` stamp runs before everything.
- Systematic LETF book: `orderRef` prefix `ETF_LS|` or `B5P|`, or membership in `data/etf_ls_universe.json` / current plan export, **unless** the ticker is in the blacklist family.

Cash and T-bill ETFs (BIL, SGOV, …) count in NAV as cash, not as idea rows.

## Drew

Empty until new fills tagged `DREW_SLEEVE`. Starts at $100k plus extra margin. Does not inherit Michael's residual names.

## Snapshot files (do not import ls-algo at runtime)

- `data/blacklist.json`
- `data/etf_to_under.json`
- `data/etf_ls_universe.json`

Refresh those JSON files when the ls-algo screener universe or blacklist changes.
