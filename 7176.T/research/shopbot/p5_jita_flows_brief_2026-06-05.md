# P5 brief — JITA flows + ETF units (7176.T) — free data plan

**Date:** 2026-06-05  
**Objective:** Fill `jita_equity_flow_bn` / `jita_etf_flow_bn` NaN columns and improve ETF AUM path.

## Free sources (no CapIQ)

| Need | Source | URL / file | Script idea |
|------|--------|------------|-------------|
| Industry equity fund flows | 投資信託協会 統計データ | https://www.toushin.or.jp/statistics/statistics/data/index.html | `download_jita_flows.py` → parse `I054B1_total_m.xlsx`, `I19521_m.xlsx` |
| ETF creation/redemption | JPX ETF PCF | https://www.jpx.co.jp/english/markets/paid-info/etf/ (portfolio CSV) | units × NAV from yfinance |
| ETF NAV history (cross-check) | yfinance | `2080.T`, `2081.T`, `2082.T` | already in P4 |
| Mutual fund NAV history | 投信総合検索ライブラリー | https://toushin-lib.fwg.ne.jp/FdsWeb/ fund **9D311082** | Vicki manual CSV only (no scrape) |

## Implementation sketch

1. `7176.T/_scripts/download_jita_flows.py` — HTTP GET Excel from toushin.or.jp, map month → `jita_equity_flow_bn`, `jita_etf_flow_bn`.
2. Extend `acquire_data.py` `fetch_jita_proxy()` to merge JITA totals where ETF-implied flow is thin.
3. Re-run `build_panel.py` → `model.py`; acceptance gate unchanged (perf H2 RMSE).

## Vicki tasks (browser)

- Confirm latest Excel filenames on toushin.or.jp statistics page (filenames change yearly).
- ETF PCF page may need JS; harvest portfolio CSV links for 2080/2081/2082 if HTTP fetch fails.

## Success criteria

- `flows_halfyear.csv` has non-NaN `jita_equity_flow_bn` for ≥8 halves.
- Dashboard AUM/flow panel shows industry context alongside filing AUM.
