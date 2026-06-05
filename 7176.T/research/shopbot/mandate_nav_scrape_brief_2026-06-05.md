# Vicki brief — P4 mandate NAV scrape (7176.T)

**Date:** 2026-06-05  
**Agent:** Marvin (HTTP scrape done); Vicki for browser follow-up  
**Objective:** Replace P4 `[Assumption]` scaffold with scraped fund NAV / AUM / returns.

## Automated (Marvin — done 2026-06-05)

`python3 7176.T/_scripts/download_mandate_nav.py` runs on every `acquire_data.py`:

**Run result:** 4 SAM PDFs saved; 137 monthly rows across 5 fund IDs; `mandate_nav_halfyear.csv` covers 6 fiscal halves (FY2023H1–FY2026H2). v4 **accepted** (perf H2 OOS RMSE ¥8,714m < v1 ¥10,307m).

| Source | URL pattern | Output |
|--------|-------------|--------|
| Value Up monthly PDF | `simplexasset.com/.../docs/0001Monthlyrpt.pdf` | NAV, AUM, 1m return |
| Orka monthly PDFs | `0004Monthlyrpt.pdf`, `0004_02`, `0004_03` | 3 months history |
| Perf ETFs 2080/2081/2082 | yfinance daily → monthly | Full history since 2019 |

Writes: `research/model/data/mandate_nav_monthly.csv`, `mandate_scrape_manifest.json`, PDFs under `data/mandate_reports/`.

## Vicki browser tasks (human-quality follow-up)

### 1. Historical SAM fund NAV (Value Up)

Simplex only exposes **latest** `0001Monthlyrpt.pdf` via static link. Browser needed for:

- [投信総合検索ライブラリー](https://toushin-lib.fwg.ne.jp/FdsWeb/) — fund code **9D311082** — export CSV if session allows (**site prohibits automated scraping**; manual browser export only)
- Orka **交付運用報告書** / **全体運用報告書** PDFs on fund page (HWM, hurdle text)
- Any **私募** / institutional fund pages under `simplexasset.com/sam/` not in `mandate_funds.json`

### 2. ETF monthly reports (JS-rendered)

`etf2080.html` etc. may need browser to capture **最新月次レポート** PDF links (HTTP fetch returned thin HTML).

### 3. Institutional mandates (81% of AUM)

Non-listed pooled mandates have **no public 受益権報告書**. Current model uses:

- Filing `aum_nonlisted_jpym` minus disclosed public SAM AUM
- Return proxy = Value Up fund half-year return `[Derived]`

Flag `[HUMAN REVIEW]` if allocator intel contradicts proxy.

## Success criteria

- `mandate_nav_detail.csv` has ≥2 funds with non-NaN `period_return` per fiscal half since FY2021
- `spec_comparison.json` **v4** `perf_fee_h2_oos_rmse` < v1 (¥10,307m) → promote v4 to production
- Else production stays **v1** (honest gate)

## Re-run

```bash
python3 7176.T/_scripts/download_mandate_nav.py
cd 7176.T/research/model && python3 build_panel.py && python3 model.py
```
