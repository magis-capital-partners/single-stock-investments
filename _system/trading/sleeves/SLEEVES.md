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
  - These rules run after the XSP and SPX rules and before the LS overlay, LS universe and owner rules; the `SPY0DTE|` / `QQQ0DTE|` / `TSLA0DTE|` / `NVDA0DTE|` / `AMZN0DTE|` stamp runs before everything except reverse-split's below.
- reverse-split (small-cap stock shorts in this account; client 60, watchdog 140 reserved; orderRef prefix `RSLIVE|`). Owner `unallocated`, strategy `reverse_split` in the hub; no book owns it, and nothing here sizes, sleeve-tags or tickets against it:
  - `reverse_split`: any order or execution stamped `RSLIVE|` (first rule of all, ahead of etf-0dte's stamp), and any ref-less row that an active claim in RS's symbol-claims file names. The file is `<IB_ACCOUNT_SYMBOL_CLAIMS_DIR>/reverse-split.json` (default `/var/lib/ib-account-claims`, written by the RS process on NY4; schema `ib_account_symbol_claims.v1`; reader `symbol_claims.py`). Rows match by conId first, symbol second, and only rows of the claim's sec type (an option on a claimed name keeps its own rule). A claim is active until its `release_after` is set and past -- age never releases one -- and a Flex statement is judged at the start of its session date, so republishing yesterday's statement after RS released a name still reads yesterday's short as RS's.
  - A claim beats the LS universe, a Drew symbol, the blacklist family and broker-matched owner evidence on the same conId: the account nets RS against any owner's shares, and only RS knows its part, so the whole position is RS's and the hub ledger ends Drew/Michael lots on that conId (as it does on etf-0dte's options).
  - `reverse_split_unverified`: while the claims directory is configured but the file is unreadable (missing, unparseable, wrong schema/system/account, one malformed entry), a ref-less short STK row that would otherwise fall to Michael's residual. In the hub it is an `ownership_review`. Names in the last good copy (kept in-process and under `IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR`, or beside the hub ledger as `symbol-claims/`) stay `reverse_split`; positive evidence (an owner ref, a Drew symbol, the blacklist family, a broker-matched opening) still wins; longs stay Michael's. The error is surfaced in the Flex snapshot's `completeness.warnings` and `symbol_claims`, and on `sync_ib`'s stderr.
  - Realized P&L: an `RSLIVE|` execution is `excluded` / `reverse_split`; a ref-less close of an RS lot (a buy-in, a corporate action) reaches RS through its opening execution's evidence (`strategy_ownership.reference_owner`); RS closing a human lot is a cross-strategy close and goes to review.
  - Where it runs: classification, the hub ledger, Flex ingest, `sync_ib` and realized history all run on NY4 (spx's user systemd: `publish-flex-book.sh`, the bridge), the host that has the claims directory. GitHub Actions and the Cloudflare edge cannot read it and never try: the hub publishes the effective claim set in the account snapshot's `completeness.symbol_claims["reverse-split"]` (only when configured), and the edge's residual fallback (`owner_residual.js`) reads that. A host with no directory at all (CI, Windows, the edge) has RS not deployed and no claims. The RS writer must leave the directory and file readable by the hub's user (`spx` on NY4) and write an empty `claims` object rather than no file: a permission error or a missing file in an existing directory reads as unreadable, which fails closed (every ticket refused, unproven shorts quarantined).
- Systematic LETF book: `orderRef` prefix `ETF_LS|` or `B5P|`, or membership in `data/etf_ls_universe.json` / current plan export, **unless** the ticker is in the blacklist family.

Cash and T-bill ETFs (BIL, SGOV, …) count in NAV as cash, not as idea rows.

## Drew

Empty until new fills tagged `DREW_SLEEVE`. Starts at $100k plus extra margin. Does not inherit Michael's residual names.

## Snapshot files (do not import ls-algo at runtime)

- `data/blacklist.json`
- `data/etf_to_under.json`
- `data/etf_ls_universe.json`

Refresh those JSON files when the ls-algo screener universe or blacklist changes.
