# Model v3 — PM diagnostics + perf crystallization

Full agent spec:

**[`_system/prompts/equity_model_v2_pm_diagnostics.md`](../../../_system/prompts/equity_model_v2_pm_diagnostics.md)**

## What changed (2026-06-05)

Prompt rewritten after P0–P3 shipped and **v2 did not improve revenue OOS RMSE** (¥4,590 vs ¥4,336). Focus shifted from "add macro factors" to **fund-level H2 crystallization** and **decomposed OOS R²**.

## Primary KPI (not total-revenue IS R²)

**Perf fee H2 OOS R²** on periods with `perf_fee > 0`. Secondary: H2 revenue OOS R² vs seasonal naive.

## Phase 1 — Diagnostics (required)

- `model_diagnostics.py` → `model_diagnostics.json`, `spec_comparison.json`, `residuals_halfyear.csv`
- IS/OOS R² per target; overfit gap; bootstrap CIs on `k_H2`, base rate
- `spec_leaderboard`: v1 vs v2 vs v3 (honest: v2 worse on level)

## Phase 2 — Dashboard (required)

- Perf fee H2 OOS R² card (lead KPI)
- IS/OOS R² bars, spec leaderboard, residual attribution (FY2024H2, FY2026H2)
- See prompt Part 6 for chart list

## Phase 3 — Data P4–P7 (best effort, gated)

| Tier | What | Why |
|------|------|-----|
| **P4** | Per-mandate NAV, hurdle, HWM, crystallization calendar | Fixes FY2026H2 −¥9.6bn miss |
| **P5** | JPX ETF units, JITA flows (fill NaN cols) | True AUM path |
| **P6** | March 3-month return into FY-end | Path-dependent crystallization |
| **P7** | Comp bridge, CapIQ paste | Ordinary/NI R² |

**Reject any spec** that worsens `perf_fee_h2` OOS RMSE vs prior stage.

## Already done (do not redo)

- P0–P3: `acquire_data.py`, `fund_registry.json`, `data/*`
- v2 blended excess in `model.py`
- Dashboard earnings panel (revenue stack, walk-forward)

## Run after implementation

```bash
cd 7176.T/research/model
python3 build_panel.py
python3 model.py
cd ../../..
python3 _system/scripts/build_dashboard_data.py
cd dashboard && python3 -m http.server 8765
```

Click **7176.T** → **Model diagnostics** (perf fee H2 OOS R² first).
