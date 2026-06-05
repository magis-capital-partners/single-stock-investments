# Prompt — Equity model visualization on the main portfolio dashboard

**Use this prompt to instruct an agent to add an etf-dashboard-quality “Models” experience to the Single Stock Investments main dashboard (`dashboard/index.html`), starting with tickers that have a built earnings/fundamental model (pilot: `7176.T`).**

Copy everything in the block below into the implementation agent. Read first: `_system/reviews/pending/dashboard_plan.md`, `dashboard/index.html`, `dashboard/darwin-viz.js`, `_system/scripts/build_dashboard_data.py`, and (if present locally) the sibling repo `etf-dashboard` (`_external/etf-dashboard` or `../etf-dashboard`).

---

## ROLE

You are a front-end + data-pipeline engineer working in the **Single Stock Investments** repo. Your job is to make Marvin’s per-ticker quantitative models **visible, honest, and beautiful** on the static portfolio dashboard — the same way the **etf-dashboard** repo makes VRP health, borrow risk, and factor panels scannable at a glance.

You are **not** rebuilding research in the browser. You **ingest** files already written under `{TICKER}/research/model/` and related research artifacts, normalize them into dashboard JSON, and render charts/tables with the existing design system.

---

## OBJECTIVE

On the **main dashboard home page** (Holdings view), let the user:

1. See at a glance which holdings have a **live model** (badge + summary strip).
2. Open a **full-width model workspace** for enabled tickers (start with **7176.T**).
3. **Visualize every major aspect** of the model: panel history, revenue identity (base vs performance fees), walk-forward accuracy vs naive benchmarks, interim nowcast, capital-structure (share count), liquidity/access warnings, Lawrence IRR vs model earnings, and links to source files on GitHub.
4. Keep the UX consistent with **etf-dashboard**: dark theme, DM Sans + JetBrains Mono, summary cards, sortable tables, Chart.js charts, no React, no production server.

**Success:** After `python _system/scripts/build_dashboard_data.py`, opening the dashboard locally and selecting `7176.T` shows a “Models” entry point and a rich model tab; GitHub Pages deploy unchanged (static files only).

---

## DESIGN REFERENCE — mirror etf-dashboard (non-negotiable)

Study these patterns from **etf-dashboard** and the existing SSI dashboard:

| Pattern | etf-dashboard / SSI equivalent |
|--------|--------------------------------|
| Build → single JSON → static HTML | `build_dashboard_data.py` → `dashboard_data.json` |
| CSS variables, card grid | `:root` in `dashboard/index.html` (`--bg-primary`, `--bg-card`, `--border`) |
| Summary strip KPIs | `#summary` / `.summary-strip` |
| Top-level view tabs | Holdings \| Darwin → add **Models** or **Model lab** |
| Chart.js module | `darwin-viz.js` (reuse library + `CHART_COLORS`) |
| Honest staleness | “as of” timestamps, amber warnings, no fake precision |
| Deep links | GitHub blob URLs via `github_blob_url()` |

**Do not** introduce React, Vite, or a Node API. **Do not** fetch arbitrary URLs at runtime in production (GitHub Pages is static). All series must be in generated JSON (or same-origin static paths under `dashboard/data/`).

---

## ARCHITECTURE

```
{TICKER}/research/model/*  +  research/*.json  +  valuation.json
              │
              ▼
_system/scripts/build_equity_model_dashboard.py   (NEW)
              │
              ├── dashboard/data/equity_models.json      (registry + per-ticker bundles)
              └── dashboard/data/equity_models/7176.T.json (optional split if JSON > ~500KB)
              │
              ▼
build_dashboard_data.py  merges summary flags into each ticker row
              │
              ▼
dashboard/index.html  +  dashboard/equity-model-viz.js  (NEW, Chart.js)
```

Wire the new builder into `build_dashboard_data.py` (call at end) so one command refreshes everything.

---

## REGISTRY — which tickers get model UI

Create `_system/portfolio/equity_model_registry.json`:

```json
{
  "enabled": ["7176.T"],
  "pilot": "7176.T",
  "notes": "Add ticker when {TICKER}/research/model/model_results.json exists"
}
```

**Ingest rule:** A ticker is `model_ready: true` only if `research/model/model_results.json` exists and `panel_halfyear.csv` has ≥ 8 rows. Otherwise omit from Models tab (holdings row may show “No model” muted badge).

---

## DATA INGEST — per ticker (7176.T pilot)

Read and normalize (units: **¥ millions** for P&L unless noted):

| Source path | Use in dashboard |
|-------------|------------------|
| `research/model/model_results.json` | Spec cards (base/perf fee forms), `walk_forward[]`, `oos_metrics`, `latest_anchor` |
| `research/model/nowcast_latest.json` | Nowcast KPI strip + caveat list |
| `research/model/panel_halfyear.csv` | Time series: revenue, base_fee, perf_fee, ordinary, net_income, aum_end_jpym, nikkei_ret, is_h2 |
| `research/model/forecasts.csv` | Scenario table (if columns: scenario, period, revenue, net_income) |
| `research/model/data_dictionary.md` | “Definitions” drawer (first 40 lines or link only) |
| `research/shares_outstanding_split_adjusted.json` | Share-count series + CAGR metadata |
| `research/market_inputs.json` | Last print, volume days, exchange (TOKYO PRO Market) |
| `research/valuation.json` | Lawrence base IRR %, stance, owner cash normalization |
| `research/equity_report_skeptical_*.md` | Link only (skeptical report) |
| `research/model/earnings_model_report.md` | Link only |

**Compress panel for JSON:** Keep last 24 half-years; round floats to 3 decimals. Do not embed full `market_monthly.csv` in v1 (too large); optionally store last 36 months of Nikkei monthly return in the bundle.

**Derived fields to compute at build time:**

- `revenue_decomp_pct`: perf_fee / (base_fee + perf_fee) per period where both exist
- `model_beats_naive`: boolean from `oos_metrics.model.rmse` vs `naive_lastyear.rmse` (7176: **false** — show honestly)
- `share_reduction_cagr_pct`: from shares JSON if present
- `liquidity_tier`: `illiquid_tpm` if market_inputs says TPM / volume days < 30 per year

---

## JSON SCHEMA — `equity_models.json` (top level)

```json
{
  "built_at": "ISO-8601",
  "chart_library": "chart.js",
  "tickers": {
    "7176.T": {
      "model_ready": true,
      "model_type": "earnings_semiannual",
      "as_of": "2026-06-04",
      "company": "Simplex Financial Holdings Co., Ltd.",
      "exchange": "TOKYO PRO Market",
      "liquidity": {
        "tier": "illiquid_tpm",
        "last_print": { "date": "2026-01-07", "price_jpy": 464, "volume_shares": 100 },
        "warning": "Retail buy restricted; confirm broker TPM / 特定投資家 access before sizing."
      },
      "lawrence": {
        "stance_gate_irr_pct": 53.33,
        "stance": "watch",
        "owner_cash_mid_cycle_jpy": 137,
        "price_today_jpy": 464
      },
      "nowcast": { "...": "copy from nowcast_latest.json" },
      "spec": {
        "base_fee": { "form": "...", "base_rate_ann_est_pct": 0.5558 },
        "perf_fee": { "form": "...", "k_H1": 0.00491, "k_H2": 0.06365 },
        "earnings_bridge": { "ord_slope": 0.579, "tax_rate": 0.264 }
      },
      "oos_metrics": { "...": "copy from model_results.json" },
      "walk_forward": [ { "label", "actual", "model", "naive_lastyear", "naive_randomwalk" } ],
      "panel": [ { "label", "period_end", "revenue", "base_fee", "perf_fee", "ordinary", "net_income", "aum_end_jpym", "nikkei_ret", "is_h2" } ],
      "shares": { "cagr_pct": 34.5, "series": [ { "date", "split_adjusted_shares" } ] },
      "links": {
        "model_report": "github blob …/earnings_model_report.md",
        "data_dictionary": "…",
        "forecasts_csv": "…",
        "build_panel": "…/build_panel.py",
        "skeptical_report": "…"
      },
      "caveats": [ "string", "..." ]
    }
  }
}
```

Also add to each entry in `dashboard_data.json` → `tickers[]`:

```json
"equity_model": {
  "ready": true,
  "as_of": "2026-06-04",
  "headline": "Nowcast H1 revenue ¥7.1bn; OOS RMSE loses to seasonal naive",
  "model_beats_naive": false
}
```

---

## UI SPEC — Holdings + Model workspace

### A. Summary strip (when any `model_ready`)

Add cards to `#summary` (Holdings view only):

- **Models live** — count enabled / ready
- **Pilot nowcast** — 7176.T revenue nowcast vs last reported H1 (if nowcast exists)
- **OOS discipline** — count tickers where `model_beats_naive === false` (amber, not red — honesty is a feature)

### B. Holdings table

New column (optional, hide on narrow screens): **Model** — badge `Live` (cyan) / `—`

### C. Detail panel (right rail) — compact teaser

When `equity_model.ready`, insert section **above** Infrastructure:

- 3 KPI mini-cards: nowcast net income, AUM anchor, OOS RMSE vs naive
- Button: **Open model workspace →** (sets selected ticker + switches view)

### D. New view tab: **Models** (recommended) OR sub-route `?view=models&ticker=7176.T`

Full-width layout (not 380px sidebar). Structure like Darwin tab:

1. **Ticker selector** — chips for `equity_model_registry.enabled` only
2. **Liquidity banner** (red/amber) for TPM / illiquid — always top for 7176
3. **KPI row** (6 cards): AUM, base fee rate, perf fee k_H2, nowcast revenue, Lawrence IRR, last print
4. **Charts** (Chart.js, destroy/recreate on ticker change like `darwin-viz.js`):
   - **Revenue stack** — grouped bar: base_fee vs perf_fee by half-year (`is_h2` shaded)
   - **Walk-forward** — line: actual vs model vs naive_lastyear (legend; tooltip shows ¥m)
   - **AUM vs Nikkei return** — dual axis or scatter (AUM level + period return bubble size = revenue)
   - **Share count** — line (split-adjusted); annotate split events from JSON
   - **OOS metrics** — horizontal bar: RMSE for model / naive_lastyear / naive_randomwalk
5. **Tables**
   - Walk-forward error table (sortable)
   - Model spec (forms + fitted coefficients) — monospace
   - Nowcast caveats — bullet list from JSON
6. **Scenario / forecasts** — if `forecasts.csv` present, render bear/base/bull rows
7. **Triangulation** (static copy for 7176, editable later): bullets linking Lawrence owner-cash vs model earnings peak; “executable return ≠ modeled IRR”
8. **Source links** — same style as deep dive links (GitHub blob)

### E. Chart implementation

- New file: `dashboard/equity-model-viz.js` — IIFE export `EquityModelViz.render(container, bundle, { escapeHtml, linkHtml })`
- Load Chart.js same CDN tag as Darwin (check `index.html` for script URL; do not duplicate version)
- Colors: reuse `CHART_COLORS` from `darwin-viz.js` or duplicate constant array
- Y-axis: format ¥ billions for large revenue (`value / 1e6` with label `¥m`)
- Tooltips: plain English (“Performance fee half”, not `perf_fee`)

### F. Mobile

- Charts stack single column
- Tables scroll horizontally inside `.table-wrap`

---

## COPY & HONESTY RULES (product requirements)

1. **Never** headline in-sample R² or “beats the market” if `oos_metrics` shows worse RMSE than `naive_lastyear`.
2. Default headline for 7176: *“Structural model explains seasonality; level forecast still loses to same-half-last-year naive.”*
3. **Liquidity/access** warning must be visible without scrolling on 7176.
4. Distinguish **Lawrence IRR** (stance gate, long horizon) from **earnings nowcast** (next half-year) — different cards, no blended KPI.
5. All numbers show `as_of` date in mono under the KPI.
6. No em dashes in UI strings.

---

## IMPLEMENTATION CHECKLIST

1. Add `_system/portfolio/equity_model_registry.json` with `7176.T`.
2. Implement `_system/scripts/build_equity_model_dashboard.py` (panel CSV parse, file existence checks, github URLs).
3. Extend `build_dashboard_data.py` to merge `equity_model` summary per ticker.
4. Add `dashboard/equity-model-viz.js` + CSS blocks in `index.html` (reuse existing tokens; add `.model-panel`, `.liquidity-banner`, `.kpi-row`).
5. Add view tab **Models** + `renderEquityModels()` in `index.html` script section.
6. Extend `selectTicker()` detail panel with model teaser + CTA.
7. Document in root `README.md` under Dashboard: rebuild command includes model bundle.
8. Test: `cd dashboard && python -m http.server 8765` — select 7176, open Models, verify charts render without console errors.
9. Keep `dashboard-pages.yml` unchanged (already deploys `dashboard/`).

---

## ACCEPTANCE CRITERIA

- [ ] `python _system/scripts/build_dashboard_data.py` writes `dashboard/data/equity_models.json` with `7176.T` populated.
- [ ] Holdings summary strip shows model count ≥ 1.
- [ ] Models tab renders 4+ charts and walk-forward table for 7176 without manual edits.
- [ ] OOS section clearly states model RMSE **worse** than seasonal naive (7176 truth).
- [ ] Liquidity banner visible for 7176 TPM.
- [ ] Clicking GitHub links opens correct `research/model/*` files.
- [ ] No new npm dependencies; Chart.js only if already used by Darwin.
- [ ] Second ticker can be enabled by adding to registry + dropping `model_results.json` (no HTML fork per ticker).

---

## FUTURE PHASES (do not block v1)

| Phase | Feature | Spec |
|-------|---------|------|
| 2 | **PM diagnostics v2** — R², IS/OOS gap, residuals, tornado, coefficient CIs | `_system/prompts/equity_model_v2_pm_diagnostics.md` |
| 3 | CapIQ ownership panel (user-upload CSV → `research/model/capiq_export.csv`) |
| 4 | Live Nikkei nowcast refresh via scheduled workflow writing `nowcast_latest.json` |
| 5 | Generic model types: `lawrence_only`, `segment_sotp`, `optionality_nav` |
| 6 | Embed etf-dashboard VRP macro strip via `_external/etf-dashboard` sync (like Darwin `import_external_data.py`) |

---

## PILOT TICKER CONTEXT — 7176.T (for copy in triangulation panel)

- **Business:** Japan asset manager / ETF sponsor; semiannual reporting only (~22 half-periods).
- **Model edge:** Performance-fee seasonality (H2 crystallization); not headline EPS level vs naive YoY.
- **Tape:** TOKYO PRO Market; ~15 volume days since 2015 listing; last print ¥464 × 100 sh.
- **Investing tension:** High Lawrence synthesis IRR vs **non-executable** public liquidity and peak success-fee year — dashboard must show both side by side.

---

## COMMAND BLOCK FOR AGENT (copy below)

```
Implement equity model visualization per _system/prompts/dashboard_equity_model_viz.md.

Pilot: 7176.T. Mirror etf-dashboard static JSON + Chart.js patterns from dashboard/darwin-viz.js.

Deliver: build_equity_model_dashboard.py, equity_models.json, equity-model-viz.js, index.html Models tab, build_dashboard_data.py merge, registry JSON, README note.

Verify locally with build_dashboard_data.py and http.server 8765. Commit with message: "dashboard: equity model viz pilot (7176.T)".
```

---

*Prompt version: 2026-06-04 · Marvin infra · pairs with `7176.T/research/earnings_model_prompt.md` and `7176.T/research/model/`.*
