# Thematic indicator panels

Broadly-ingested macro / industry context that explains *why* holdings' optionality reprices. Consumed narrowly by tagged tickers only.

## Files

| Path | Contents |
|------|----------|
| `manifest.json` | Latest value, YoY, direction, staleness per series, grouped by theme |
| `{series_id}.csv` | Append-only history (`date,value`) per indicator |
| `filing_panels/*.csv` | Filing-derived time series (TPL water, AZLCZ leases, hyperscaler capex) |

## Pipeline (daily order)

```bash
python -m darwin.import_external_data          # from _system/scripts; sync etf-dashboard
python _system/scripts/extract_theme_facts.py
python _system/scripts/fetch_theme_panel.py
python _system/scripts/apply_context_overlay.py
python _system/scripts/fetch_ls_microstructure.py
python _system/scripts/fetch_peer_panel.py
```

- **Config:** `_system/scripts/theme_panel_config.json`
- **Tags:** `_system/portfolio/holdings_themes.json` (`"*"` expands to all registry holdings for `macro_regime`)
- **Sources:** FRED (rates, credit, gas, WTI), Yahoo daily (fallback when FRED/Stooq blocked), etf-dashboard CSV/JSON, EIA (Permian; needs `EIA_API_KEY`), repo `ai_overlay`, filing panels.

## etf-dashboard submodule

Live data: `_external/etf-dashboard` (see `.gitmodules`). Override path with `DARWIN_ETF_DASHBOARD_ROOT`. Synced snapshots also land in `_system/reference/market-data/external/` for offline CI.

## Rules

- **Context only.** Every indicator carries `in_base_irr: false`. Tailwinds inform stance and overlay sizing; they never auto-inflate Lawrence base IRR.
- Promotion to base case requires a human to set `in_base_irr: true` (preserved across refreshes) under **[HUMAN REVIEW]**.
- Offline-safe: on network failure, cached CSV history is kept; Yahoo proxies used for WTI/VIX/GLD when FRED times out.
- Deep dives: `#### Thematic context` in Business & moat (mechanical table + Marvin narrative preserved on refresh).

## Themes

| Theme | Chain | Tagged holdings |
|-------|-------|-----------------|
| `ai_power_land` | AI compute -> power -> grid/water -> land/hosting | TPL, LB, WBI, APLD, BWEL, **AZLCZ** |
| `macro_regime` | HY OAS, rates, dollar, VIX, credit impulse | All registry holdings (`*`) |
| `gold_royalties` | Gold spot, GDX, GDX/GLD ratio | RGLD, FNV, WPM, OR, MSB (sleeve pulse) |
| `exchange_volatility` | VIX, realized vol, VRP health | CME, ICE, CBOE, MIAX, 8697.T |
| `iron_ore_steel` | Iron ore spot + steel ETF + Cliffs shipments + Mesabi royalty facts | **MSB** |

### MSB operator automation

```bash
python _system/scripts/parse_msb_royalty_report.py --write
python _system/scripts/fetch_theme_panel.py --theme iron_ore_steel
python _system/scripts/build_msb_operator_model.py --write
```

Writes `MSB/research/evidence/royalty_report_latest.json` and `MSB/research/operator_model.json`. Hooked into `marvin_cloud_refresh.py MSB`. Context only — does not rewrite base IRR.

See `_system/frameworks/optionality_valuation.md` § **Thematic context layer**.
