# Safeties

All gates fail closed. There is no UI override except `execution.allow_live` in `config.yaml`.

## Session

- Connect only to `127.0.0.1`.
- Bind the account from `IBKR_ACCOUNT`. Refuse if TWS is on another account.
- Drew uses client ID 71, Michael 72. Do not use 0, 17, 41, 87, 90, or ls-algo worker offsets.
- NY4 Gateway and this local TWS cannot be logged in at the same time.

## Order

- `dry_run: true` until `allow_live: true`.
- Live send also requires retyping the ticker on the confirm card.
- Limit orders only. No market, no options, no SPXW, no OTC, no crypto.
- USD stocks/ETFs, SMART/NYSE/NASDAQ/AMEX/ARCA.
- Quote age must be under `quote_max_age_seconds` (15).
- Last may not move more than `price_band_pct` (1%) between propose and approve.
- `proposal_id` is one-shot.
- Same-ticker cooldown (10 minutes).
- Kill file `_system/trading/sleeves/KILL` blocks everything.

## Sizing

- Drew: max $25k per order, 20% of $100k per name, 12 names, max gross $200k.
- Michael: YAML caps; NAV from last classified residual book.
- BUY that would breach sleeve gross is rejected.

## Name filters

- Drew cannot submit systematic LETF names (`ETF_LS` / `B5P` / universe snapshot) or blacklist-family names (those are Michael's).
- Michael can submit blacklist-family names (JPM, BRK-B, AXP, APLD, SMR, CBRS and wrappers such as APLZ).
- Michael cannot submit SPXW or systematic LETF plan names.
- Neither owner can submit SPY, QQQ, TSLA, NVDA or AMZN, shares or options. They are etf-0dte's: its 0DTE executors trade the options in this account, and an assignment delivers shares overnight for its 09:30 unwind to sell. A sleeve SELL could sell that delivery, and a BUY could net against it. The hub's order loop refuses the same contracts on IBKR's identity of the conId (`allocation_policy.etf_0dte_ticket_refusal`). Before 2026-11-10 an NVDA or AMZN option classified as a Drew LS overlay, so either owner's desk could submit one (their shares were already refused as systematic LETF names); both are refused now.
- Neither owner can submit a name reverse-split claims (`RSLIVE|` small-cap stock shorts, client 60, watchdog 140 reserved), either side and any sec type: a BUY covers RS's short, a SELL adds to it, and an option delivers shares on exercise. The claims are RS's symbol-claims file (`IB_ACCOUNT_SYMBOL_CLAIMS_DIR`, default `/var/lib/ib-account-claims`; `symbol_claims.py`), matched on conId or symbol / underlying. While that directory is configured but its file cannot be read, every sleeve order is refused: nothing is proven unclaimed. The hub's order loop refuses the same tickets (`allocation_policy.reverse_split_ticket_refusal`).

## Logging

JSON logs under `_system/trading/sleeves/logs/` (gitignored). Local store under `data/local/` (gitignored).
