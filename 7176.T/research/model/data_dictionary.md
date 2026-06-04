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

## Known gaps / to acquire (would materially improve the model)

- **Per-ETF NAV × units** (daily, JPX/Simplex) → high-frequency ETF-AUM nowcast.
- **Per-fund NAV vs hurdle / high-water mark** → performance-fee crystallization timing.
- **AUM by category pre-2023** and **base/perf split pre-FY2024** → extends component history.
- **JITA industry flows**, **TSE investor-type flows** → net-flow vs mark-to-market split.
- **CapIQ** ownership + peer fee/comp ratios → Bayesian priors.
