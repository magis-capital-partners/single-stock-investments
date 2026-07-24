# World Model linkages

Cross-ticker derivation graph for thesis KPIs. **Context only.**

Does not author valuation. Never rewrite universal-contract components, Power Zone routes, IC packets, `human_decision.json`, or legacy Lawrence `inputs` / `scenarios` / `implied_return`. See `proof_first_valuation.md` § *Do not mix two valuation languages*.

## Layout

| Path | Role |
|------|------|
| `manifest.json` | Edge registry (theme series → ticker KPI ids) |
| `derived_metrics.json` | Latest resolved values (hot, overwrite) |
| `{TICKER}/research/kpi_ledger.json` | Curated 5–15 thesis KPIs; optional `prediction_role` |
| `_system/reference/world_model/themes/` | Theme prediction cards (phase / interference / reinforcement) |
| `_system/reference/world_model/superorg/` | Superorg scorecards (first portfolio: ICE) |
| `_system/reference/world_model/expert_horizons/` | Public quote trackers (AGI, robotaxi; context only) |
| `_system/reference/industry/` | 13 industry nodes (11 thesis + 2 horizon). Taxonomy: `world_model/README.md` |
| `_system/scripts/apply_world_model_context.py` | Writes `world_model_context` on valuation.json (context only) |
| `_system/proposals/world_model_autolink_valuation_2026-07-23.md` | Auto-link plan (Phases 1–5 live; promotion human-gated) |
| `_system/reference/kpi/history/{YYYY-MM}.json` | Monthly cold snapshot |
| `dashboard/data/world_model.json` | Morning strip v2 (passes, cards, Superorgs, horizons) |

## Rules

- Broad ingest via theme panels; narrow consume via `holdings_themes.json` + ledger binds.
- Fail / stale → `[OPEN DILIGENCE]` on `binds_to.valuation_path` (agent re-fetch + `[Assumption]`); do not rewrite `inputs` / `scenarios` / `implied_return`.
- `in_base_irr` stays `false` unless dual-agent promote (capital names still human-gated).
- Do not duplicate `kpi_trends.json` into ledgers. Trends are mechanical; ledgers are thesis-narrow.

## Commands

```bash
python _system/scripts/resolve_linkages.py --update-ledgers
python _system/scripts/check_kpi_ledger.py --write --mark-auto
python _system/scripts/lint_kpi_ledger.py
python _system/scripts/build_world_model_snapshot.py
python _system/scripts/ci_rebuild_profile.py world-model-weekly
```

`fetch_theme_panel.py` remains the fetcher. Linkages are the graph + write policy into `derived_metrics.json` and optional ledger `actual` fields.

## Pilot edges + ledger coverage

1. `hyperscaler_capex_to_land_power` → TPL / APLD / LB ledgers
2. `gold_spot_to_royalty_sentiment` → RGLD / MSB ledgers
3. `vix_to_exchange_vol_context` → ICE ledger (US); foreign venues use home realized series from `exchange_vol_map.json`

## Operating rules (tight)

- Context only — never auto-edit `inputs` / `scenarios` / `implied_return`
- Cap 5–15 KPIs; every row binds to a valuation path or stance-only note
- **Fail** = decision input; **stale feed with null actual** = ops/agent re-fetch; filing annuals with a value are not auto-stale
- Weekly CI: Data Pipeline cron `0 16 * * 0` (Sunday UTC) → profile `world-model-weekly`
- Agent weekend pass: open strip → triage fails → annotate `[Assumption]` or `[OPEN DILIGENCE]` (not a human inbox)

```bash
python _system/scripts/ci_rebuild_profile.py world-model-weekly
```
