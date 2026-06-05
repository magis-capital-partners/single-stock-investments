# Prompt — Improve equity earnings models + PM-grade diagnostics (v2)

**Use this prompt to instruct an analyst/agent to upgrade `{TICKER}/research/model/` and the dashboard model panel with the statistics and charts a multi-manager (Millennium-style) pod PM expects: honest R², out-of-sample discipline, component attribution, uncertainty, and scenario response — without overselling a ~12-point semiannual sample.**

Copy everything in the block below into the modeling agent. Read first:

- `{TICKER}/research/earnings_model_prompt.md` (v1 build spec)
- `{TICKER}/research/model/earnings_model_report.md`, `model.py`, `model_results.json`
- `_system/prompts/dashboard_equity_model_viz.md` (dashboard ingest + UI)
- `dashboard/equity-model-viz.js`, `_system/scripts/build_equity_model_dashboard.py`

**Pilot ticker:** `7176.T` (Simplex Financial Holdings). Design must generalize to future `{TICKER}/research/model/` builds.

---

## ROLE

You are a quantitatively rigorous equity analyst on a multi-manager pod. Your PM does not want a single headline R². They want:

1. **Decomposed fit** (base fee identity vs convex performance fee vs earnings bridge).
2. **In-sample vs out-of-sample** side by side, with the gap visible (overfit alarm).
3. **Benchmark dominance** stated plainly (we currently lose to seasonal naive on revenue level).
4. **Uncertainty** on every coefficient and forecast (bootstrap / posterior intervals, not fake precision).
5. **Actionable charts** on the dashboard when the user clicks the ticker.

Your job is **model v2 + diagnostics export + dashboard panels**. Not a black-box ML dump.

---

## CURRENT STATE (7176.T — do not re-litigate, build on it)

| What works | What is missing |
|------------|-----------------|
| Revenue identity decomposition (base + perf) | No R² / adjusted R² exported per component |
| H1/H2 crystallization seasonality (`k_H2 >> k_H1`) | No residual diagnostics |
| Walk-forward OOS RMSE/MAPE vs naive | No in-sample vs OOS R² comparison chart |
| Scenario fan (`forecasts.csv`) | No prediction intervals on nowcast |
| Dashboard: revenue stack, walk-forward, OOS RMSE bar | No actual-vs-fitted scatter, residual plot, tornado, coefficient stability |
| Honest report that model loses to naive on level | PM cannot see R² at a glance |

**Binding constraint unchanged:** ~12 semiannual P&L points → **≤3–4 free parameters per sub-equation**, regularization, walk-forward validation.

---

## OBJECTIVE (two deliverables)

### A. Model v2 (Python)

Upgrade `model.py` (or add `model_diagnostics.py` called from `model.py`) to compute and persist a full **diagnostics bundle** while preserving the structural revenue identity.

### B. Dashboard v2 (static JSON + Chart.js)

Extend `build_equity_model_dashboard.py` and `equity-model-viz.js` so clicking a ticker with a model shows **PM-grade panels** including R² (with honest labeling).

---

## PART 1 — METRICS THE PM MUST SEE

Compute for **each target** below. Targets:

| Target | Series | Notes |
|--------|--------|-------|
| `revenue_total` | Half revenue (¥m) | Primary stance gate for model quality |
| `base_fee` | Base fee half (¥m) | Identity fit; expect high in-sample R² where fee split disclosed |
| `perf_fee` | Performance fee half (¥m) | Convex line; report R² only on periods with `perf_fee > 0` |
| `ordinary_profit` | Ordinary profit (¥m) | Bridge fit |
| `net_income` | Parent net income (¥m) | End of bridge |

For **each target**, report **both**:

- **In-sample (IS):** fit on full estimation sample (post-2018, document exclusion rule).
- **Out-of-sample (OOS):** expanding-window walk-forward (same protocol as v1; do not change definition mid-series without documenting).

### Required statistics (per target × IS/OOS)

| Stat | Definition | PM use |
|------|------------|--------|
| `r2` | 1 − SS_res/SS_tot | Explained variance (label clearly IS or OOS) |
| `adj_r2` | 1 − (1−R²)(n−1)/(n−k−1) | Penalize parameter count; **k** = free params in that sub-equation |
| `rmse` | Root mean squared error (¥m) | Scale error |
| `mae` | Mean absolute error (¥m) | Robust error |
| `mape_pct` | Mean abs % error | Scale-free (flag when actual ≈ 0) |
| `directional_hit` | Sign(match Δpred, Δactual) | Trading-relevant |
| `theil_u` | RMSE_model / RMSE_naive_rw | <1 beats random walk |
| `n` | Observations used | Always show sample size |
| `n_params` | Free parameters | Pair with adj_r2 |

### Required benchmark block (OOS only)

For each target, compare structural model against:

1. **Naive same-half-last-year** (current v1 benchmark — likely winner on revenue level).
2. **Naive random walk** (last period level).
3. **Structural naive:** `base_rate × AUM` only (no perf fee) — shows value of convex leg.
4. **Optional:** seasonal dummy + Nikkei return only (2-parameter sanity check).

Report **loss differential**: `rmse_model − rmse_naive` and whether model wins.

### Uncertainty (mandatory for coefficients)

Bootstrap (≥1,000 resamples, block-bootstrap by fiscal year if needed) or Bayesian linear regression with weak priors for:

- `base_rate_ann`
- `k_H1`, `k_H2`
- `ord_slope`, `ord_intercept`, `tax_rate`

Export **5th / 50th / 95th percentile** for each. At n≈12, prefer **bootstrap percentile CIs** over OLS t-stats.

### Overfit diagnostic (mandatory headline)

```
overfit_gap = r2_in_sample − r2_out_of_sample   (per target)
```

Display on dashboard. If gap > 0.15 on revenue, amber banner: *"In-sample fit overstates predictive power."*

### Optional (implement if scipy available; else stub with `[HUMAN REVIEW]`)

- **Diebold-Mariano** p-value: model vs naive_lastyear loss differential (revenue).
- **Ljung-Box** on OOS residuals (autocorrelation = missing dynamics).

---

## PART 2 — MODEL IMPROVEMENTS (prioritized ROI)

Implement in order. Each upgrade must re-run walk-forward and **beat or match** prior OOS on at least one dimension (RMSE on perf_fee, directional hit, or scenario response) or be rejected.

### Tier 1 — Data (highest ROI; expands effective n)

1. **Per-ETF NAV × units** for every Simplex-listed ETF (daily → aggregate to half-year).
   - New series: `aum_etf_nowcast`, `etf_flows_half`
   - Source: JPX ETF pages, Simplex IR, `1306.T` / `1570.T` proxies
2. **JITA monthly net flows** (equity + ETF category) → `net_flows_half` in panel.
3. **Value / PBR factor return** (TOPIX value vs growth or custom low-PBR basket) as second driver for perf fee alongside Nikkei.

### Tier 2 — Specification (still ≤4 params per equation)

4. **Separate AUM drivers:** `aum_nonlisted` vs `aum_etf` with different base fee rates (2 rates max).
5. **Perf fee:** `max(0, w1×Nikkei + w2×value_factor − hurdle)` with **one** convexity weight (not 10 factors).
6. **Cost bridge:** variable comp = `comp_ratio × perf_fee` test; headcount × fixed cost per head for fixed opex.
7. **H1 perf fee:** explicit low-weight crystallization flag (do not force H1 ≈ 0 in sample).

### Tier 3 — Nowcast & scenarios

8. **Monthly nowcast** with **80% prediction interval** (bootstrap forecast error from walk-forward).
9. **Tornado chart** inputs: Nikkei H2 return, value factor, AUM level, comp ratio, USD/JPY.
10. **CapIQ overlay** (user-upload CSV path: `research/model/capiq_export.csv`): ownership %, TPM volume history — qualitative panel, not in regression until verified.

### Tier 4 — Rejected unless OOS improves

- Kitchen-sink multivariate OLS on 20 macro variables.
- LSTM / XGBoost on 12 points without strong regularization and worse OOS than structural form.
- In-sample R² as the primary marketing number.

---

## PART 3 — FILES TO PRODUCE / UPDATE

Under `{TICKER}/research/model/`:

| File | Purpose |
|------|---------|
| `model.py` | Extend to emit diagnostics (or import `model_diagnostics.py`) |
| `model_diagnostics.json` | **New** — full PM diagnostics bundle (schema below) |
| `model_results.json` | Merge summary + pointer to diagnostics (backward compatible) |
| `residuals_halfyear.csv` | period, target, actual, fitted, residual, is_oos flag |
| `coefficient_bootstrap.json` | CIs for k_H1, k_H2, base_rate, bridge |
| `forecasts.csv` | Add columns: `revenue_lo80`, `revenue_hi80`, `net_income_lo80`, `net_income_hi80` |
| `earnings_model_report.md` | New § **PM diagnostics** with IS/OOS table per target |
| `figures/` (optional PNG) | `actual_vs_fitted.png`, `residuals.png`, `tornado.png` — or JSON-only for dashboard |

Regenerate panel: `python build_panel.py && python model.py`

---

## PART 4 — `model_diagnostics.json` SCHEMA

```json
{
  "as_of": "YYYY-MM-DD",
  "estimation_window": { "start": "2018-H1", "end": "2026-H2", "n_halfyears": 12, "excluded": "pre-2018 HK legacy" },
  "targets": {
    "revenue_total": {
      "in_sample": { "r2": 0.0, "adj_r2": 0.0, "rmse_jpym": 0, "mae_jpym": 0, "mape_pct": 0, "directional_hit": 0, "theil_u": 0, "n": 0, "n_params": 3 },
      "out_of_sample": { "r2": 0.0, "adj_r2": 0.0, "rmse_jpym": 0, "mae_jpym": 0, "mape_pct": 0, "directional_hit": 0, "theil_u": 0, "n": 0 },
      "overfit_gap": 0.0,
      "benchmarks_oos": {
        "naive_lastyear": { "rmse_jpym": 0, "r2": 0.0, "beats_model": true },
        "naive_randomwalk": { "rmse_jpym": 0, "r2": 0.0 },
        "structural_base_only": { "rmse_jpym": 0 }
      }
    },
    "base_fee": { "...": "same shape" },
    "perf_fee": { "...": "same shape; note zero-inflation in caveats" },
    "ordinary_profit": { "...": "same shape" },
    "net_income": { "...": "same shape" }
  },
  "coefficients": {
    "base_rate_ann": { "point": 0.0056, "p05": 0.0051, "p50": 0.0056, "p95": 0.0061, "method": "bootstrap" },
    "k_H1": { "point": 0.0049, "p05": 0.0, "p50": 0.0049, "p95": 0.01 },
    "k_H2": { "point": 0.0636, "p05": 0.04, "p50": 0.0636, "p95": 0.09 },
    "ord_slope": { "point": 0.579, "p05": 0.45, "p50": 0.579, "p95": 0.68 }
  },
  "walk_forward": [ { "label", "target", "actual", "fitted", "residual", "naive_lastyear" } ],
  "residual_summary": { "mean_jpym": 0, "std_jpym": 0, "max_abs_jpym": 0 },
  "tornado": [ { "driver": "Nikkei H2 return", "low": -0.1, "high": 0.14, "eps_delta_pct": 0 } ],
  "nowcast_interval": { "revenue_p50": 0, "revenue_p05": 0, "revenue_p95": 0 },
  "caveats": [ "string" ],
  "version": "v2_pm_diagnostics"
}
```

**R² rules for JSON and UI:**

- Always pair `r2` with `n` and `n_params`.
- Show **OOS R²** larger font than IS R² on dashboard.
- If OOS R² < 0, display as negative (model worse than mean) — do not floor at zero.
- Subscript labels in UI: "R² out-of-sample" not "R²" alone.

---

## PART 5 — DASHBOARD CHARTS (Millennium PM panel)

Extend `equity-model-viz.js` when user clicks ticker. Add section **Model diagnostics** below existing earnings charts.

### KPI strip (add 4 cards)

| Card | Value |
|------|-------|
| OOS R² revenue | `targets.revenue_total.out_of_sample.r2` + n |
| IS vs OOS gap | `overfit_gap` with amber if >0.15 |
| OOS RMSE vs naive | delta + winner badge |
| Perf fee OOS R² | on non-zero perf periods only |

### Charts (Chart.js — new canvas IDs)

| # | Chart | Type | Data source |
|---|-------|------|-------------|
| 1 | **Actual vs fitted** | Scatter + 45° line | `walk_forward` or `residuals_halfyear.csv`; annotate OOS R² |
| 2 | **IS vs OOS R² by target** | Grouped bar | `targets.*.in_sample.r2` vs `out_of_sample.r2` for 5 targets |
| 3 | **Residuals over time** | Line + bar | `residuals_halfyear.csv`; color OOS points |
| 4 | **Residual distribution** | Histogram | OOS residuals only |
| 5 | **Coefficient stability** | Line with ribbon | Expanding-window `k_H2` + bootstrap p05/p95 |
| 6 | **Tornado / sensitivity** | Horizontal bar | `tornado[]` — EPS or net income delta |
| 7 | **Scenario fan** | Line + shaded band | `forecasts.csv` + interval columns |
| 8 | **Component waterfall** | Stacked bar (one period) | base + perf → revenue → ordinary → net income |
| 9 | **H2/H1 seasonality** | Grouped bar by FY | revenue H1 vs H2 (already in report table — visualize) |
| 10 | **Benchmark loss** | Horizontal bar | RMSE: model vs naive_lastyear vs naive_rw vs base_only |

### Tables

- **PM scorecard:** target × IS R² × OOS R² × adj R² × RMSE × beats naive? 
- **Coefficient CI table:** point, p05, p95
- **Diebold-Mariano** (if computed): test name, p-value, interpretation one line

### Honest copy (static, 7176.T)

> Structural model explains **seasonality and convexity**; **level forecast** may trail same-half-last-year naive when revenue trends up. Use for pre-report nowcast and scenario response, not as sole EPS estimate.

---

## PART 6 — INGEST PIPELINE UPDATE

Extend `_system/scripts/build_equity_model_dashboard.py`:

1. Load `model_diagnostics.json` if present; merge into `equity_models.json` tickers[ticker].diagnostics`.
2. Load `residuals_halfyear.csv` → compact JSON array (round 3 dp).
3. Load `coefficient_bootstrap.json`.
4. Add `diagnostics_ready: true` flag on ticker row.

Run: `python _system/scripts/build_dashboard_data.py`

---

## PART 7 — VALIDATION CHECKLIST

- [ ] `model_diagnostics.json` exists with all 5 targets × IS/OOS metrics.
- [ ] OOS R² for revenue is **honest** (likely low or negative vs naive — document, do not hide).
- [ ] `overfit_gap` computed and visible on dashboard.
- [ ] Bootstrap CIs on `k_H2` show wide uncertainty (expected at small n).
- [ ] Dashboard shows **Actual vs fitted** scatter and **IS vs OOS R²** bar chart for 7176.T.
- [ ] `earnings_model_report.md` updated with PM diagnostics section.
- [ ] v1 `model_results.json` consumers still work (backward compatible fields preserved).
- [ ] No em dashes in dashboard UI strings.

---

## PART 8 — IMPLEMENTATION ORDER (agent workflow)

1. Read v1 `model.py` + panel; document estimation sample.
2. Add `compute_r2`, `compute_adj_r2`, `walk_forward_diagnostics()` — unit-test on synthetic 6-point series.
3. Implement bootstrap CIs for coefficients.
4. Write `model_diagnostics.json` + `residuals_halfyear.csv`.
5. Tier 1 data attempt: at minimum wire **value factor return** column into `build_panel.py` (Yahoo `1306.T` or TOPIX value proxy).
6. Re-run walk-forward; update `earnings_model_report.md`.
7. Extend `build_equity_model_dashboard.py` ingest.
8. Extend `equity-model-viz.js` with charts 1–6 (minimum); 7–10 if time.
9. `python build_panel.py && python model.py && python _system/scripts/build_dashboard_data.py`
10. Verify locally: click 7176.T → see OOS R² card + IS/OOS bar chart.

---

## COMMAND BLOCK FOR AGENT (copy below)

```
Implement equity model v2 PM diagnostics per _system/prompts/equity_model_v2_pm_diagnostics.md.

Ticker: 7176.T.

Deliver: model_diagnostics.json, residuals_halfyear.csv, coefficient_bootstrap.json, updated model.py + earnings_model_report.md, dashboard ingest + equity-model-viz.js charts (actual vs fitted, IS/OOS R² bars, residuals, tornado).

Honesty: show OOS R² even if negative; show overfit gap; state naive_lastyear beats model on revenue RMSE unless data upgrade changes it.

Verify: build_panel.py → model.py → build_dashboard_data.py → localhost:8765 → click 7176.T.

Commit: "7176.T: model v2 PM diagnostics + dashboard R² panels"
```

---

## APPENDIX — Why PMs want these specific views

| PM question | Chart / metric |
|-------------|----------------|
| "Is this overfit?" | IS vs OOS R² gap |
| "Does it beat a dumb benchmark?" | RMSE vs naive + Diebold-Mariano |
| "Where does error live?" | Residual plot by half; perf fee vs base fee R² |
| "How stable is the convexity?" | Expanding-window k_H2 + bootstrap band |
| "What moves EPS?" | Tornado |
| "What do we think next print?" | Nowcast + 80% interval |
| "Can I trust direction?" | Directional hit + IC |

---

*Prompt version: 2026-06-04 · pairs with `earnings_model_prompt.md`, `dashboard_equity_model_viz.md`, `7176.T/research/model/`.*
