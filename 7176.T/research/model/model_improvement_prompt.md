# Model v2 — PM diagnostics & dashboard upgrade

Full agent spec:

**[`_system/prompts/equity_model_v2_pm_diagnostics.md`](../../../_system/prompts/equity_model_v2_pm_diagnostics.md)**

## What this adds

- **R² and adjusted R²** per target (revenue, base fee, perf fee, ordinary, net income), **in-sample and out-of-sample**
- **Overfit gap** (IS R² minus OOS R²)
- Bootstrap confidence intervals on `k_H1`, `k_H2`, base rate, earnings bridge
- Dashboard charts: actual vs fitted scatter, IS/OOS R² bars, residuals, tornado, coefficient stability

## Current gap (v1)

`model_results.json` has OOS RMSE/MAPE only — no R². Dashboard shows walk-forward lines but not PM scorecard.

## After implementation

```bash
cd 7176.T/research/model
python3 build_panel.py
python3 model.py
cd ../../..
python3 _system/scripts/build_dashboard_data.py
cd dashboard && python3 -m http.server 8765
```

Click **7176.T** → **Model diagnostics** section with R² panels.

## Data upgrades (priority)

1. Per-ETF NAV × units (daily)
2. JITA net flows
3. Value/PBR factor return alongside Nikkei
4. Optional CapIQ CSV: `research/model/capiq_export.csv`
