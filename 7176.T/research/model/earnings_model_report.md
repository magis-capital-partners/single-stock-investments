# 7176.T — Earnings model report

**Simplex Financial Holdings (TOKYO PRO Market)**
**As of:** 2026-06-05 · **Author:** Marvin (quant pod build)
**Code:** `build_panel.py` → `model.py` → `nowcast.py` · **Data:** `panel_halfyear.csv`, `data_dictionary.md`

> Honest-accuracy build per `../earnings_model_prompt.md`. Asset-manager revenue is
> nearly an accounting identity, so we decompose rather than dump variables, fit few
> parameters, and validate **out-of-sample** against naive benchmarks.

---

## 1. The single most important finding: H2 crystallization seasonality

Revenue is **strongly back-half loaded** because performance (success) fees crystallize at the **March fiscal year-end**.

| Fiscal year | H1 revenue (¥m) | H2 revenue (¥m) | H2 ÷ H1 |
|-------------|-----------------|-----------------|---------|
| FY2021 | 3,075 | 8,990 | 2.9× |
| FY2022 | 3,526 | 4,303 | 1.2× |
| FY2023 | 3,319 | 5,586 | 1.7× |
| FY2024 | 3,805 | 11,162 | 2.9× |
| FY2025 | 5,353 | 10,901 | 2.0× |
| FY2026 | 5,578 | 16,934 | 3.0× |

Performance fees by half (¥m, disclosed/derived): H1 stays small (**0.9–2.0bn**); H2 carries the load (**7.3–12.6bn**). **Any model that ignores this seasonality is wrong by construction.**

---

## 2. Revenue identity and fitted components

```
Revenue_half = BaseFee_half + PerfFee_half + Other
BaseFee_half = base_rate/2 × avg_AUM           (recurring)
PerfFee_half = k_half × avg_AUM × max(0, Nikkei_return − hurdle)   (convex, crystallization-weighted)
```

### Base fee — highly predictable identity

- **Effective base rate ≈ 0.51%–0.56% per year** (annualized), mild upward drift (mix shift toward higher-fee active/thematic ETFs and mandates).
- `base_fee_half ≈ 0.0056/2 × avg_AUM`. On ~¥1.34tn AUM that is **~¥3.7bn per half** of recurring fee — the floor under revenue.

### Performance fee — the convex alpha

Fitted no-intercept slopes on `avg_AUM × max(0, Nikkei return)`:

| Coefficient | Value | Meaning |
|-------------|-------|---------|
| `k_H1` | ~0.0049 | Small interim crystallization |
| `k_H2` | ~0.064 | **~13× larger** — the March year-end take |

This is the heart of the model: when Japan equities rally into March, H2 performance fees spike (FY2026 success fees **+53.6%** on AUM **+2.9%**). The convex `max(0, return)` form captures the asymmetry (down markets → ~0 perf fee, not negative).

### Earnings bridge

- `ordinary ≈ −157 + 0.579 × revenue` (¥m): ~**58% incremental ordinary margin** → strong operating leverage (small fixed cost base, ~55 staff).
- Effective **tax rate ≈ 26.4%**; `net_income ≈ ordinary × (1 − 0.264)`. NCI (Simplex Heritage 40%) currently immaterial.

---

## 3. Out-of-sample validation (expanding-window walk-forward)

Predicting **total half revenue**, inputs known before the print (seasonality + Nikkei return), vs naive benchmarks. **9 OOS half-year predictions.**

| Model | OOS RMSE (¥m) | OOS MAPE | Directional hit |
|-------|---------------|----------|-----------------|
| Structural reduced-form | 4,336 | 32.6% | 0.67 |
| **Naive (same half last year)** | **3,230** | **30.2%** | **1.00** |
| Naive (random walk) | 5,636 | 58.1% | 0.11 |

### Honest read (do not oversell)

- The structural model **does not beat "same half last year" on level accuracy** at this sample size. The revenue series **trends up**, so a same-half-last-year benchmark is hard to beat and has a perfect directional record by construction.
- The model **crushes random walk** (which ignores seasonality) — confirming the H2 crystallization structure is real and the dominant signal.
- **Where the model actually adds edge** (and naive cannot):
  1. **Conditional response** to market moves within the period (scenario fan, §4).
  2. **Live nowcasting** before the print as markets move (§5).
  3. A **decomposition** that tells you *why* (base vs perf), enabling targeted expert triangulation on the perf line.

### v2 driver (P0–P3 data layer, blended excess return)

After wiring `acquire_data.py` (ETF NAV, factor returns, fund proxy), walk-forward **v2** replaces raw Nikkei with `effective_excess_ret` (fund NAV proxy when available, else 0.65×Nikkei + 0.35×value factor):

| Model | OOS RMSE (¥m) | OOS MAPE | Directional hit |
|-------|---------------|----------|-----------------|
| v1 (Nikkei only) | 4,336 | 32.6% | 0.67 |
| v2 (blended excess) | 3,977 | 30.3% | 0.89 |
| v3a (March window on H2) | 5,407 | — | — |
| Naive (same half last year) | 3,230 | 30.2% | 1.00 |

**Honest read:** v2 improves directional hit (0.67 → 0.89) but **still loses to seasonal naive on RMSE**. v3a (Jan–Mar crystallization window on H2) **worsens** both revenue RMSE and perf-fee H2 RMSE vs v1. **Production spec stays v1** per `spec_comparison.json`. Registry-weighted fund proxy and filing-anchored ETF AUM remain coarse; **JITA flows and true per-fund NAV/hurdle remain the binding gap.**

---

## 3b. PM diagnostics (model_diagnostics.json)

Decomposed in-sample and out-of-sample R² per target. **Primary KPI:** perf fee on H2 halves with perf > 0.

| Target | IS R² | OOS R² | OOS RMSE (¥m) | Naive LY beats? |
|--------|-------|--------|---------------|-----------------|
| Revenue (total) | −0.69 | −0.01 | 4,336 | Yes (¥3,230) |
| Revenue (H2 only) | −1.88 | −0.56 | 5,631 | Yes |
| Base fee | 0.45 | −2.14 | 318 | — |
| Perf fee | −0.14 | −2.63 | 8,547 | — |
| **Perf fee (H2, perf>0)** | — | **−14.25** | **10,307** | n=2 only |
| Ordinary profit | — | — | — | See JSON |

**Honest read:**

- Total revenue **OOS R² ≈ 0** (slightly negative): model ties noise; seasonal naive wins on level.
- Base fee IS R² ~0.45 on n=4 disclosed splits: identity works where data exists.
- Perf fee OOS R² deeply negative: crystallization miss dominates (FY2024H2, FY2026H2 in `residual_attribution`).
- **Production spec: v4** (P4 mandate-weighted excess). Beats v1 on perf-fee H2 OOS RMSE (¥8,714m vs ¥10,307m). v2/v3a rejected.

**Spec leaderboard (OOS):**

| Spec | Rev OOS RMSE | Perf H2 OOS RMSE | Default |
|------|--------------|------------------|---------|
| v1 | ¥4,336m | ¥10,307m | no |
| v2 | ¥3,977m | ¥44,744m | no |
| v3a | ¥5,407m | ¥11,863m | no |
| v4 | ¥4,833m | ¥8,714m | **yes** |

Regenerate: `python3 model.py` (runs `model_diagnostics.py` automatically).

### Dashboard PM panel (Phase 2)

Portfolio dashboard **7176.T → Model diagnostics** ingests `model_diagnostics.json`, `spec_comparison.json`, `coefficient_bootstrap.json`, and `residuals_halfyear.csv`. Lead KPI: **perf fee H2+ OOS R²** (not in-sample total revenue). Charts: IS/OOS R² bars, spec leaderboard, actual-vs-fitted scatter, residual bars, H2 NI tornado. Rebuild: `python3 _system/scripts/build_equity_model_dashboard.py`.

---

## 4. Scenario fan (next interim and next full-year H2)

Revenue/earnings as a function of the Nikkei return over the half (¥m):

| Horizon | Scenario | Nikkei ret | Revenue | Ordinary | Net income |
|---------|----------|-----------|---------|----------|------------|
| Next H1 | bear | −10% | 3,726 | 2,001 | 1,472 |
| Next H1 | base | +3% | 4,167 | 2,256 | 1,660 |
| Next H1 | bull | +12% | 4,969 | 2,721 | 2,002 |
| Next H2 | bear | −10% | 3,726 | 2,001 | 1,472 |
| Next H2 | base | +4% | 7,454 | 4,161 | 3,061 |
| Next H2 | bull | +14% | 16,907 | 9,636 | 7,089 |

`forecasts.csv` now includes **80% intervals** (`revenue_lo80`/`hi80`, `net_income_lo80`/`hi80`) from walk-forward OOS residual standard deviation.

**Tornado (EPS sensitivity), largest first:** H2 Nikkei return → performance fee (dominant, convex); AUM level → base fee; value/PBR factor spread (proxy, to add); USD/JPY (HK/overseas); comp ratio. The asymmetry is stark: **a weak-market H2 collapses earnings to roughly the base-fee floor**, while a strong H2 multiplies them.

---

## 5. Live nowcast (`nowcast.py`)

Re-runnable monthly. Uses:
- Filing AUM anchor (¥1,335.7bn, Mar-2026)
- Live ETF basket AUM from `data/etf_aum_daily.csv` (filing-anchored NAV scaling; 13 tickers)
- ETF implied flows from `data/etf_flows_daily.csv`
- v1 (Nikkei) and v2 (0.65×Nikkei + 0.35×value) perf drivers

Output: `nowcast_latest.json` (includes `nowcast_jpym` and `nowcast_v2_jpym`).

Caveats: H1 perf-fee nowcast is low-confidence; JITA industry flows still pending; non-listed fund hurdle uses registry [Assumption].

### P4 / P6 data layer (Phase 3)

- **P6 March window:** `march_window_halfyear.csv` — Jan–Mar return into March FY-end for H2 crystallization (`march_nikkei_ret`, `march_value_ret`, `march_blended_ret`). Drives **v3a** spec in `model.py`.
- **P4 Mandate NAV scaffold:** `mandate_nav_halfyear.csv` — registry-weighted mandate excess vs hurdle [Assumption]. Replace with 受益権報告書 per-fund NAV when scraped (Vicki).

---

## 6. Honest limitations

- **Sample size:** ~12 half-year P&L points; base-fee/AUM detail only from FY2024/2023. Coefficients carry wide uncertainty; treat point forecasts as central tendencies, not precision.
- **Structural breaks:** 2023 PBR-reform theme, FY2026 perf-fee spike, 10:1 (2023) and 20:1 (2025) splits, legacy-HK wind-down. Pre-2018 data deliberately excluded from coefficient fitting.
- **v2 drivers still coarse:** ETF AUM uses filing anchor × NAV ratio (not true units); non-listed perf proxy uses registry weights [Assumption].
- **JITA flows pending:** ETF implied flows are [Derived]; industry flow columns are NaN until scrape.
- **Crystallization timing risk:** exact hurdle/high-water-mark dates per fund are not in the public PRO-Market disclosure; this is where expert calls and NAV scraping earn their keep.

---

## 7. Triangulation hooks (where edge compounds)

- **True ETF units** (JPX/Simplex, not Yahoo) → replace filing-anchored AUM scaling; **scrape fund NAVs vs hurdle** → read perf-fee crystallization before disclosure.
- **Expert/channel calls** (allocators, ex-staff, Aizawa LP market maker) → net-flow and mandate intel the model can't see.
- **ToSTNeT buyback/cancellation notices** → share-count for EPS (see `../shares_outstanding_split_adjusted.json`; ~34%/yr split-adjusted share reduction).
- State explicitly where the **quant nowcast agrees or diverges** with qualitative intel and size conviction accordingly.

---

## Files

| File | Purpose |
|------|---------|
| `acquire_data.py` | P0–P6 data layer → `data/*.csv`, `data_acquisition_manifest.json` |
| `fund_registry.json` | Simplex ETF list, AUM pools, factor proxies, non-listed fund assumptions |
| `build_panel.py` | Filing panel + market + merge acquired data → `panel_halfyear.csv` |
| `model.py` | Fit v1/v2/v3a components, walk-forward CV → `model_results.json`, `forecasts.csv` |
| `model_diagnostics.py` | IS/OOS R² per target → `model_diagnostics.json`, `spec_comparison.json`, `residuals_halfyear.csv` |
| `nowcast.py` | Live monthly nowcast (ETF AUM + flows + v2) → `nowcast_latest.json` |
| `data_dictionary.md` | Every series, unit, source, tag |
