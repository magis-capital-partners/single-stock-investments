# ls-algo underlyings: automated power-zone valuation plan

**Date:** 2026-07-17
**Status:** implemented (orchestrator shipped to main)
**Related:** `_system/proposals/valuation_ui_redesign_2026-07-16.md`, `_system/proposals/investment_committee_remaining_phases_2026-07-14.md`, `_system/frameworks/power_zones.json`

## Goal

Every `ls_algo_underlying` holding flows through one nightly pipeline: power zones → method routing → workbench → entry pricing → gated Investment Committee → dashboard refresh. Decisions stay with the human owner.

## Pipeline

```text
ls-algo sleeve tickers
  → build_power_zones.py
  → build_valuation_workbench.py (route + decision status)
  → build_power_zone_pricing.py (seed config if needed; 10/12/15/20% hurdles)
  → IC gates (decision-grade + price/live/flag trigger)
  → refresh_valuation_dashboard_rows.py / build_dashboard_data.py
```

Command:

```powershell
python _system/scripts/darwin/run_ls_algo_valuation_pipeline.py
```

Nightly: `ci_rebuild_profile.py` profile `full` runs the orchestrator with `--skip-dashboard` before `build_dashboard_data.py`.

## IC rules

1. Gate-triggered only (never whole sleeve)
2. Power-zone route personas seat the raters (`select_raters`)
3. Automation stops at `owner_decision_pending`

## Implementation record

| Piece | Path |
|---|---|
| Orchestrator | `_system/scripts/darwin/run_ls_algo_valuation_pipeline.py` |
| Rater selection | `investment_committee_pipeline.py` `select_raters()` |
| Pricing seed | `build_power_zone_pricing.py` `seed_default_config()` |
| CI wire | `ci_rebuild_profile.py` `full` profile |
| Tests | `test_ls_algo_valuation_pipeline.py`, committee + pricing tests |
