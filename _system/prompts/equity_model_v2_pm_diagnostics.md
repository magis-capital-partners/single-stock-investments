# Prompt — Equity model v3: PM diagnostics + perf-crystallization data (7176.T)

**Use this prompt to instruct an analyst/agent to upgrade `{TICKER}/research/model/` and the dashboard model panel.** The PM (Citadel / Millennium-style) cares about **decomposed out-of-sample R²**, not a single in-sample headline. The binding problem on 7176.T is **H2 performance-fee crystallization**, not base-fee identity.

Copy everything below into the modeling agent. Read first:

| File | Why |
|------|-----|
| `{TICKER}/research/earnings_model_prompt.md` | v1 revenue identity + sample-size law |
| `{TICKER}/research/model/earnings_model_report.md` | Honest OOS read |
| `{TICKER}/research/model/model.py`, `model_results.json` | Current fit + walk-forward |
| `{TICKER}/research/model/acquire_data.py`, `fund_registry.json`, `data/` | P0–P3 layer (done) |
| `{TICKER}/research/model/data_dictionary.md` | Series tags |
| `_system/prompts/dashboard_equity_model_viz.md` | Dashboard ingest |
| `dashboard/equity-model-viz.js`, `_system/scripts/build_equity_model_dashboard.py` | UI |

**Pilot ticker:** `7176.T` (Simplex Financial Holdings). Generalize file paths to `{TICKER}/research/model/` for future builds.

---

## ROLE

You are a quantitatively rigorous equity analyst on a multi-manager pod. Your PM wants:

1. **Decomposed fit** — base fee (identity) vs perf fee (convex crystallization) vs earnings bridge.
2. **Out-of-sample R² first** — in-sample R² paired with overfit gap; never market IS R² alone.
3. **Benchmark honesty** — seasonal naive likely wins total revenue **level** while revenue trends up; say so.
4. **Uncertainty** — bootstrap CIs on `k_H1`, `k_H2`, base rate, bridge (n≈12 → wide bands expected).
5. **Actionable dashboard** — R² scorecard, residuals by leg, tornado, nowcast intervals.

**Not in scope:** kitchen-sink ML, 20-factor OLS on 12 points, optimizing in-sample total-revenue R².

---

## CURRENT STATE (7176.T — build on this, do not restart)

### What exists (merged to `main`)

| Layer | Status | Files |
|-------|--------|-------|
| Revenue identity v1 | Done | `model.py`, `build_panel.py` |
| P0–P3 data acquisition | Done | `acquire_data.py`, `fund_registry.json`, `data/*` |
| v2 blended excess driver | Done | `perf_fee_model_v2` in `model_results.json` |
| Walk-forward OOS RMSE/MAPE | Done | `oos_metrics`, `oos_metrics_v2` |
| Dashboard model panel | Done | `equity-model-viz.js`, `equity_models.json` |
| PM diagnostics (R² bundle) | **Not done** | `model_diagnostics.json` missing |
| Fund-level crystallization | **Not done** | Still `k_H2 × AUM × macro return` |

### Empirical results (do not ignore)

**Walk-forward OOS (9 half-years, total revenue):**

| Spec | RMSE (¥m) | MAPE | Directional hit |
|------|-----------|------|-----------------|
| v1 (Nikkei) | 4,336 | 32.6% | 0.67 |
| v2 (blended excess) | **4,590** | 35.9% | **0.89** |
| Naive same-half-last-year | **3,230** | 30.2% | 1.00 |

**v2 data layer did not improve level accuracy.** Registry weights and filing-anchored ETF AUM (Yahoo lacks Japan ETF units) are too coarse. Directional hit improved; RMSE worsened.

**Largest residuals (where R² is lost):**

| Half | Actual (¥m) | v1 model | Miss | Driver |
|------|---------------|----------|------|--------|
| FY2024H2 | 11,162 | 9,382 | −1,780 | Strong March crystallization |
| FY2026H2 | 16,934 | 7,335 | **−9,599** | PBR/value rally + perf spike (+53.6% YoY) |
| FY2025H2 | 10,901 | 3,075 | −7,826 | Weak market; model stuck on base floor |

**Conclusion:** R² uplift requires **fund-level perf crystallization** and **March return path**, not more macro factors blended into one `effective_excess_ret`.

### R² by leg (expected today)

| Target | IS R² (expect) | OOS R² (expect) | Bottleneck |
|--------|----------------|-----------------|------------|
| Base fee | High (0.85+) | Moderate | AUM disclosure gaps pre-2023 |
| **Perf fee (H2)** | Low | **Very low** | No hurdle/HWM/fund NAV |
| **Perf fee (H2, perf>0)** | Low | **Primary KPI** | Same |
| Total revenue | Moderate IS | Below naive | Dominated by perf leg |
| Ordinary / NI | Moderate | Follows revenue | Comp bridge coarse |

**Primary optimization target:** `perf_fee` OOS R² on H2 halves with `perf_fee > 0`, then `revenue_total` H2-only OOS R².

---

## OBJECTIVE (three deliverables)

### A. PM diagnostics bundle (Python)

Add `model_diagnostics.py` (imported from `model.py`) emitting full IS/OOS metrics per target. Preserve v1 `model_results.json` fields for backward compatibility.

### B. Model v3 — perf crystallization spec (Python)

Upgrade perf-fee equation toward the revenue identity in `earnings_model_prompt.md`:

```
PerfFee_half = Σ_fund ( perf_eligible_AUM_f × max(0, NAV_f/NAV_f_hwm − 1) × perf_rate_f × cryst_flag_f )
```

Until fund-level data exists, implement **staged fallbacks** (document which stage is active):

| Stage | Driver | Accept only if… |
|-------|--------|-----------------|
| v1 | `k_half × AUM × max(0, Nikkei)` | Baseline (current) |
| v2 | `k_half × AUM × effective_excess_ret` | Beats v1 on **perf_fee OOS RMSE** or H2 revenue OOS RMSE |
| v3a | v2 + **March 3-month return** into fiscal year-end | Beats v2 on H2 perf OOS |
| v3b | **Per-fund summed excess** from `mandate_nav_halfyear.csv` | Beats v3a on perf_fee OOS R² |
| v4 | v3b + **JITA flows** in AUM roll-forward | Beats v3b on nowcast MAE |

**Rejection rule:** Any new spec must log `spec_comparison.json` showing OOS metrics vs prior stage. If worse on perf_fee RMSE, keep prior stage as production default.

### C. Dashboard PM panel (JSON + Chart.js)

Extend ingest + `equity-model-viz.js` per Part 5. **Lead with perf-fee OOS R²**, not total-revenue IS R².

---

## PART 1 — METRICS THE PM MUST SEE

### Targets

| ID | Series | Notes |
|----|--------|-------|
| `revenue_total` | Half revenue (¥m) | Full sample |
| `revenue_h2_only` | H2 revenue only | **Secondary KPI** — crystallization leg |
| `base_fee` | Base fee half (¥m) | Identity fit |
| `perf_fee` | Perf fee half (¥m) | Convex leg |
| `perf_fee_h2_positive` | H2 periods with perf > 0 | **Primary KPI** |
| `ordinary_profit` | Ordinary (¥m) | Bridge |
| `net_income` | Parent NI (¥m) | Bridge end |

For each target: **in-sample** and **out-of-sample** (expanding-window walk-forward, same protocol as v1).

### Required statistics (per target × IS/OOS)

| Stat | PM use |
|------|--------|
| `r2` | Explained variance — **show OOS larger than IS in UI** |
| `adj_r2` | Penalize k; always pair with `n` and `n_params` |
| `rmse`, `mae`, `mape_pct` | Scale errors (¥m) |
| `directional_hit` | Sign(Δpred) vs sign(Δactual) |
| `theil_u` | RMSE_model / RMSE_naive_rw |
| `n`, `n_params` | Sample discipline |

### Benchmark block (OOS)

Compare each target against:

1. **Naive same-half-last-year** (likely winner on trending revenue).
2. **Naive random walk**.
3. **Structural base-only** (`base_rate × AUM`, no perf).
4. **Seasonal dummy + Nikkei** (2-parameter sanity check).

Report `rmse_model − rmse_naive` and `r2_model − r2_naive`.

### Overfit diagnostic (mandatory)

```
overfit_gap = r2_in_sample − r2_out_of_sample
```

Dashboard amber banner if `overfit_gap > 0.15` on `revenue_total` or `perf_fee_h2_positive`.

### Uncertainty

Bootstrap (≥1,000; block-bootstrap by fiscal year) for: `base_rate_ann`, `k_H1`, `k_H2`, `ord_slope`, `ord_intercept`, `tax_rate`. Export p05/p50/p95.

### Optional

- Diebold-Mariano: model vs naive_lastyear (revenue, perf_fee_h2).
- Ljung-Box on OOS residuals.

---

## PART 2 — DATA ACQUISITION (P4–P7, evidence-ranked)

P0–P3 is **done** (`acquire_data.py`). Do not re-scaffold. Extend with:

### P4 — Perf crystallization microstructure (highest R² ROI)

| Series | Granularity | Source | Output file |
|--------|-------------|--------|-------------|
| Per-mandate / per-fund NAV | Monthly → half | 受益権報告書, trust reports, Simplex IR | `mandate_nav_monthly.csv` |
| Hurdle, HWM, perf rate | Per fund | Fund terms, offering docs | `mandate_terms.json` |
| Crystallization calendar | Per fund | H1/H2/March flags | extend `fund_registry.json` |
| Historical perf fee by bucket | Half-year | Filings pre-FY2024 backfill | `perf_fee_by_bucket_halfyear.csv` |

**Model use:** Replace `k_H2 × AUM × Nikkei` with summable fund-level excess. This is the only path to explain FY2024H2 / FY2026H2 spikes.

### P5 — True AUM path (medium ROI)

| Series | Source | Output | Status |
|--------|--------|--------|--------|
| JPX ETF units (creation/redemption) | JPX statistics | `etf_units_daily.csv` | Replaces filing-anchored scaling |
| JITA net flows (equity, ETF) | [toushin.or.jp](https://www.toushin.or.jp/) | `flows_monthly.csv` (fill NaN cols) | Columns exist, values empty |
| TSE investor-type flows | JPX | `investor_flows_monthly.csv` | New |

**Model use:** `AUM_t = AUM_{t-1} × (1+r) + net_flows` — improves base-fee level and perf scaling.

### P6 — Return path (refine v2, conditional ROI)

| Series | Source | Output |
|--------|--------|--------|
| March 3-month return (into FY-end) | Compute from `^N225`, value ETFs | `march_window_ret_halfyear.csv` |
| Per-strategy returns (2080/2081/2082, 2516, 1356) | Yahoo daily | extend `factor_returns_*` |
| Perf-eligible AUM weights (observed, not registry) | Filings + ETF units | `perf_eligible_aum_halfyear.csv` |

**Model use:** Crystallization is path-dependent — Oct dip + Feb–Mar rally ≠ flat half-average return.

### P7 — Bridge and context (lower revenue R² impact)

| Series | Source | Output |
|--------|--------|--------|
| Quarterly opex / headcount | Filings, CapIQ paste | `comp_bridge_halfyear.csv` |
| CapIQ ownership, TPM volume | User CSV | `capiq_peers.csv` |
| "Other" revenue breakdown | MD&A | `other_revenue_halfyear.csv` |

### Data acceptance gate

After each P-tier, re-run walk-forward and append to `data_acquisition_manifest.json`:

```json
{
  "tier": "P4",
  "oos_delta": {
    "perf_fee_h2_rmse": -500,
    "perf_fee_h2_r2": 0.15,
    "revenue_total_rmse": -200
  },
  "accepted": true,
  "production_spec": "v3b"
}
```

**Reject tier** if `perf_fee_h2_rmse` does not improve vs prior tier (unless explicit `[HUMAN REVIEW]` reason documented).

---

## PART 3 — SPECIFICATION UPGRADES (≤4 params per equation)

Implement only after data exists or as explicit fallback:

1. **March window driver:** `perf_drive = AUM × max(0, ret_mar_3m − hurdle)` — 1 extra timing param max.
2. **Split base rates:** `rate_nonlisted` vs `rate_etf` (2 rates) — only if AUM split reliable.
3. **Variable comp:** `VariableComp ≈ α × perf_fee` — test if ordinary R² gains.
4. **H1 perf:** separate low `k_H1` with crystallization flag; do not force zero.

**Rejected unless OOS perf_fee improves:** multivariate OLS on >4 macro factors, LSTM/XGB on 12 points.

---

## PART 4 — FILES TO PRODUCE / UPDATE

| File | Purpose |
|------|---------|
| `model_diagnostics.py` | IS/OOS R², benchmarks, bootstrap |
| `model_diagnostics.json` | Full PM bundle (schema below) |
| `spec_comparison.json` | v1 vs v2 vs v3 OOS leaderboard |
| `residuals_halfyear.csv` | period, target, actual, fitted, residual, is_oos |
| `coefficient_bootstrap.json` | CIs |
| `acquire_data.py` | Add P4–P7 functions (extend, don't replace P0–P3) |
| `model.py` | Stage selector + diagnostics hook |
| `earnings_model_report.md` | § PM diagnostics + § Data tier results |
| `forecasts.csv` | Add `revenue_lo80`, `revenue_hi80` |

Regenerate: `python3 build_panel.py && python3 model.py`

---

## PART 5 — `model_diagnostics.json` SCHEMA

```json
{
  "as_of": "YYYY-MM-DD",
  "production_spec": "v1|v2|v3a|v3b|v4",
  "primary_kpi": "perf_fee_h2_positive.out_of_sample.r2",
  "estimation_window": { "start": "2018-H1", "end": "2026-H2", "n_halfyears": 12 },
  "targets": {
    "perf_fee_h2_positive": {
      "in_sample": { "r2": 0.0, "adj_r2": 0.0, "rmse_jpym": 0, "n": 0, "n_params": 2 },
      "out_of_sample": { "r2": 0.0, "rmse_jpym": 0, "n": 0 },
      "overfit_gap": 0.0,
      "benchmarks_oos": {
        "naive_lastyear": { "rmse_jpym": 0, "r2": 0.0, "beats_model": false }
      }
    },
    "revenue_total": { "...": "same shape" },
    "revenue_h2_only": { "...": "same shape" },
    "base_fee": { "...": "same shape" },
    "perf_fee": { "...": "same shape" },
    "ordinary_profit": { "...": "same shape" },
    "net_income": { "...": "same shape" }
  },
  "coefficients": {
    "k_H2": { "point": 0.064, "p05": 0.04, "p50": 0.064, "p95": 0.09, "method": "bootstrap" }
  },
  "spec_leaderboard": [
    { "spec": "v1", "perf_fee_h2_oos_rmse": 0, "perf_fee_h2_oos_r2": 0, "revenue_oos_rmse": 4336 },
    { "spec": "v2", "perf_fee_h2_oos_rmse": 0, "perf_fee_h2_oos_r2": 0, "revenue_oos_rmse": 4590 }
  ],
  "residual_attribution": [
    { "label": "FY2026H2", "target": "perf_fee", "actual": 14316, "fitted": 0, "residual": 0, "note": "March crystallization miss" }
  ],
  "walk_forward": [],
  "tornado": [],
  "nowcast_interval": {},
  "caveats": [],
  "version": "v3_pm_diagnostics"
}
```

**R² display rules:**

- OOS R² **larger font** than IS in dashboard.
- Negative OOS R² allowed (model worse than mean).
- Always show `n` and `n_params` beside R².
- UI label: "R² out-of-sample (perf fee, H2)" not "R²" alone.

---

## PART 6 — DASHBOARD CHARTS

Add section **Model diagnostics** below existing earnings charts.

### KPI strip (priority order)

| Card | Value |
|------|-------|
| **Perf fee H2 OOS R²** | Primary |
| Revenue OOS R² | Secondary |
| IS vs OOS overfit gap | Amber if >0.15 |
| OOS RMSE vs naive | Delta + winner |
| Production spec | v1 / v2 / v3 badge |

### Charts (minimum 6)

| # | Chart | Type |
|---|-------|------|
| 1 | Actual vs fitted (perf fee H2) | Scatter + 45° line |
| 2 | IS vs OOS R² by target | Grouped bar (7 targets) |
| 3 | Residuals over time | Bar; color H2 OOS |
| 4 | Spec leaderboard | Bar (v1/v2/v3 OOS RMSE) |
| 5 | Coefficient stability | `k_H2` expanding window + bootstrap band |
| 6 | Tornado (H2 EPS sensitivity) | Horizontal bar |
| 7 | Scenario fan + 80% band | Line + shade |
| 8 | H1 vs H2 revenue by FY | Grouped bar |
| 9 | Benchmark RMSE comparison | Horizontal bar |
| 10 | Residual attribution table | FY2024H2, FY2026H2 callouts |

### Honest static copy (7176.T)

> Model explains **seasonality and convexity structure**. **Level forecast** may trail same-half-last-year naive while revenue trends up. **Perf-fee H2 OOS R²** is the quality gate. Use for pre-report nowcast and scenario response, not as sole EPS estimate.

---

## PART 7 — INGEST PIPELINE

Extend `build_equity_model_dashboard.py`:

1. Load `model_diagnostics.json`, `spec_comparison.json`, `residuals_halfyear.csv`.
2. Merge into `equity_models.json` → `tickers[ticker].diagnostics`.
3. Set `diagnostics_ready: true`, `production_spec`, `primary_kpi`.

Run: `python3 _system/scripts/build_dashboard_data.py`

---

## PART 8 — VALIDATION CHECKLIST

- [ ] `model_diagnostics.json` with all targets × IS/OOS (including `perf_fee_h2_positive`, `revenue_h2_only`).
- [ ] `spec_leaderboard` documents v1 vs v2 (v2 worse on revenue RMSE — honest).
- [ ] Primary KPI card shows **perf fee H2 OOS R²**, not total revenue IS R².
- [ ] `overfit_gap` visible; amber when >0.15.
- [ ] Bootstrap CIs on `k_H2` (wide expected).
- [ ] Residual attribution flags FY2024H2 / FY2026H2.
- [ ] P4+ data attempt documented in manifest (even if partial).
- [ ] v1 `model_results.json` backward compatible.
- [ ] No em dashes in dashboard UI strings.

---

## PART 9 — IMPLEMENTATION ORDER

1. Read `model.py`, `model_results.json`, `acquire_data.py` — document production spec (v1 vs v2).
2. Implement `model_diagnostics.py`: `compute_r2`, walk-forward per target, benchmarks.
3. Emit `model_diagnostics.json`, `residuals_halfyear.csv`, `coefficient_bootstrap.json`, `spec_comparison.json`.
4. **P4 attempt:** scaffold `mandate_nav_monthly.csv` from trust reports or `[Assumption]` proxy; wire v3b if data exists.
5. **P5 attempt:** JITA scrape or manual CSV → fill `flows_monthly.csv` NaNs; JPX ETF units if scrapeable.
6. **P6:** add `march_window_ret` to panel; test v3a vs v2 on H2 perf OOS only.
7. Update `earnings_model_report.md` § PM diagnostics + honest spec comparison.
8. Dashboard ingest + charts 1–6 minimum.
9. `python3 build_panel.py && python3 model.py && python3 _system/scripts/build_dashboard_data.py`
10. Verify: localhost:8765 → 7176.T → perf fee H2 OOS R² card visible.

---

## COMMAND BLOCK FOR AGENT (copy below)

```
Implement equity model v3 per _system/prompts/equity_model_v2_pm_diagnostics.md.

Ticker: 7176.T.

Phase 1 (required): model_diagnostics.py + model_diagnostics.json + spec_comparison.json
  — Primary KPI: perf_fee_h2_positive OOS R²
  — Document v2 regression vs v1 (revenue OOS RMSE 4590 vs 4336)

Phase 2 (required): dashboard PM panel — perf fee H2 OOS R² card, IS/OOS bar chart,
  spec leaderboard, residual attribution for FY2024H2/FY2026H2

Phase 3 (best effort): P4 mandate NAV scaffold + v3a March window driver;
  reject any spec that worsens perf_fee H2 OOS RMSE

Honesty: negative OOS R² OK; naive_lastyear may beat model on revenue level — state plainly.

Verify: build_panel.py → model.py → build_dashboard_data.py → click 7176.T.

Commit: "7176.T: model v3 PM diagnostics + perf crystallization spec"
```

---

## APPENDIX — PM question → metric map

| PM question | Answer in model |
|-------------|-----------------|
| "Where is R² lost?" | `perf_fee_h2_positive` OOS; residual attribution table |
| "Did the data upgrade help?" | `spec_leaderboard` + manifest `oos_delta` |
| "Is this overfit?" | `overfit_gap` per target |
| "Does it beat a dumb benchmark?" | OOS RMSE vs naive; Diebold-Mariano |
| "What moves H2 EPS?" | Tornado on March return, AUM, perf rate |
| "What do we think next print?" | `nowcast_interval` 80% band |
| "Can I trust direction?" | `directional_hit` (v2 already 0.89) |

---

*Prompt version: 2026-06-05 · supersedes 2026-06-04 draft · pairs with `earnings_model_prompt.md`, `acquire_data.py` (P0–P3), `dashboard_equity_model_viz.md`.*
