# 7176.T model — data dictionary

All financials hand-extracted from primary filings (English machine translations in
`7176.T/research/evidence/_text_en/`). Japanese fiscal year ends **31 March**;
**H1** = Apr–Sep (中間/interim), **H2** = Oct–Mar (contains the year-end performance-fee crystallization).

## panel_halfyear.csv (primary modeling frame)

| Column | Unit | Tag | Source / definition |
|--------|------|-----|---------------------|
| `fy` | year | [Filing] | Fiscal year ending March |
| `half` | H1/H2 | [Derived] | Interim vs second half |
| `period_end` | date | [Derived] | Half-year end (Sep-30 or Mar-31) |
| `revenue` | JPY thousand | [Filing] | 営業収益; H2 = annual − H1 |
| `ordinary` | JPY thousand | [Filing] | 経常利益; H2 = annual − H1 |
| `net_income` | JPY thousand | [Filing] | 親会社株主に帰属する純利益; H2 = annual − H1 |
| `base_fee` | JPY thousand | [Filing] | 基本報酬 (H1 disclosed in interim MD&A) |
| `perf_fee` | JPY thousand | [Filing] | 成功報酬 (H1 disclosed in interim MD&A) |
| `headcount` | persons | [Filing] | 従業員数 (FY2026 H1 def. change: incl. secondees) |
| `aum_end_jpym` | JPY million | [Filing] | 運用資産残高 total (億円 ×100) |
| `aum_nonlisted_jpym` | JPY million | [Filing] | Non-listed trusts/funds |
| `aum_etf_jpym` | JPY million | [Filing] | Listed ETF AUM |
| `aum_avg_jpym` | JPY million | [Derived] | mean(this end, prior end) |
| `nikkei_ret` | ratio | [Market] | ^N225 return over the fiscal half |
| `topix_etf_ret` | ratio | [Market] | 1306.T (TOPIX ETF) return over the half |
| `usdjpy_ret` | ratio | [Market] | JPY=X change over the half |
| `nk_lev_ret` | ratio | [Market] | 1570.T (Nikkei leveraged ETF) — lev/inverse & vol proxy |
| `*_vol` | ann. ratio | [Market] | Realized daily vol annualized over the half |
| `is_h2` | 0/1 | [Derived] | Crystallization flag |
| `base_fee_rate_ann` | ratio | [Derived] | base_fee/avg_AUM ×2 (annualized) |

## Derived fee splits (in `model.py`)

| Series | Tag | Source |
|--------|-----|--------|
| Annual perf fee FY2024 ¥8,907m | [Filing] | 20240627 MD&A (+203.1% YoY) |
| Annual base/perf FY2026 (¥7,869m / ¥14,316m) | [Filing] | Pnotice2026-1 |
| Annual base/perf FY2025 (¥6,720m / ¥9,320m) | [Derived] | Back-out from FY2026 YoY (+17.1% / +53.6%) |
| H1 base/perf FY2024–26 | [Filing] | Interim MD&A 業績概要 |
| H2 fees | [Derived] | Annual − H1 |

## Market drivers (market_monthly.csv)

Daily closes (auto-adjusted) from Yahoo Finance: `^N225`, `1306.T`, `JPY=X`, `1570.T`,
aggregated to fiscal-half returns and realized volatility in `build_panel.py`.

## Acquired data layer (`data/`, `acquire_data.py`)

Run `python3 acquire_data.py` (or `build_panel.py`, which calls it first). Manifest:
`data/data_acquisition_manifest.json`.

### P0 — ETF NAV × units + fund return proxy

| File | Tag | Definition |
|------|-----|------------|
| `etf_nav_daily.csv` | [Market] | Daily NAV per Simplex ETF ticker (Yahoo) |
| `etf_aum_daily.csv` | [Derived] | NAV × shares outstanding → AUM per ETF |
| `fund_return_halfyear.csv` | [Derived] | Weighted ETF basket return per fiscal half |
| `fund_nav_proxy_halfyear.csv` | [Derived/Assumption] | Perf-eligible excess from registry weights + benchmarks |

### P1 — Flows + AUM pools

| File | Tag | Definition |
|------|-----|------------|
| `etf_flows_daily.csv` | [Derived] | ΔAUM − return×prior AUM per ETF |
| `flows_monthly.csv` | [Filing/Market] | Simplex ETF implied flows + JITA B-1 equity/ETF net flows (億円) |
| `jita_flows_monthly.csv` | [Market] | JITA B-1 scrape: `jita_equity_net_flow_bn_jpy`, `jita_etf_net_flow_bn_jpy` |
| `flows_halfyear.csv` | [Derived] | Half-year sum of `etf_implied_flow_jpym` |
| `aum_pools_halfyear.csv` | [Derived] | Perf-eligible vs base-fee AUM split |

### P2 — Fee history + factor returns

| File | Tag | Definition |
|------|-----|------------|
| `fee_history_raw.csv` | [Filing] | Regex extract from evidence `_text/` |
| `fee_history_halfyear.csv` | [Filing/Derived] | Curated base/perf fee by half |
| `factor_returns_daily.csv` | [Market] | Nikkei, value, growth, REIT, lev proxies |
| `factor_returns_monthly.csv` | [Market] | Monthly factor returns |
| `factor_returns_halfyear.csv` | [Derived] | Half-year factor returns incl. `value_factor_ret` |

### P3 — Comp bridge + CapIQ template

| File | Tag | Definition |
|------|-----|------------|
| `comp_bridge_halfyear.csv` | [Filing] | Revenue, perf fee, opex, headcount bridge |
| `capiq_peers.csv` | [Pending] | Template for CapIQ / peer fee ratios |

### P4 — Mandate NAV (scraped + derived)

| File | Tag | Definition |
|------|-----|------------|
| `mandate_nav_monthly.csv` | [Filing/Market/Derived] | Monthly NAV/AUM/return per fund from SAM PDFs + yfinance ETFs; `download_mandate_nav.py` |
| `mandate_nav_detail.csv` | [Filing/Market/Derived] | Per-mandate half-year return, benchmark, excess, AUM weights |
| `mandate_nav_halfyear.csv` | [Filing/Market/Derived] | `mandate_weighted_excess`, `mandate_crystallization_ret` (H2 HWM path), `mandate_march_ret`, `mandate_weighted_return`, `mandate_count` |
| `mandate_scrape_manifest.json` | [Market] | PDF download log + fund IDs |
| `mandate_reports/` | [Filing] | Saved SAM monthly PDFs |

### P6 — March crystallization window

| File | Tag | Definition |
|------|-----|------------|
| `march_window_halfyear.csv` | [Market/Derived] | Jan–Mar return into March FY-end for H2 halves: `march_nikkei_ret`, `march_value_ret`, `march_blended_ret` (0.65×Nikkei + 0.35×value on positive leg). H1 rows fall back to full-half `nikkei_ret`. Feeds **v3a** perf driver in `model.py`. |

### Panel columns merged from `data/`

`perf_eligible_excess_ret`, `etf_perf_basket_ret`, `value_factor_ret`, `etf_basket_ret`,
`etf_implied_flow_jpym`, `perf_eligible_aum_jpym`, `nonlisted_share`, `etf_share`,
`opex_sga_jpy_million`, `incremental_margin`, `march_nikkei_ret`, `march_value_ret`,
`march_blended_ret`, `mandate_weighted_excess`, `mandate_crystallization_ret`, `mandate_march_ret`, `mandate_count`.

## Remaining gaps

- **JITA industry flows** — P5 scrape fills `jita_equity_flow_bn` / `jita_etf_flow_bn` (億円) from B-1 Excel; `download_jita_flows.py`.
- **Per-fund NAV vs hurdle / high-water mark** — P4 live for FY2023H1 onward (6 halves); pre-2023 and institutional pool still proxy [Derived]. Vicki: 投信総合検索ライブラリー CSV for Value Up history.
- **AUM by category pre-2023** and **base/perf split pre-FY2024** — extends component history.
- **CapIQ** ownership + peer fee/comp ratios — paste into `capiq_export.csv`.
