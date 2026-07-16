# Market data for Darwin IRA backtests

Populated by `_system/scripts/download_ira_research.py`.

| Path | Contents |
|------|----------|
| `returns/{TICKER}.csv` | Monthly returns (Yahoo or synthetic) |
| `benchmarks/spy_us.csv` | SPY daily (Stooq) |
| `benchmarks/bnd_us.csv` | Bond ETF proxy |
| `french/` | Fama-French 5-factor monthly |
| `macro/` | FRED CPI, 10Y, VIX |
| `commodities/` | Spot inputs (copper) via `fetch_market_inputs.py` |
| `themes/` | Thematic indicator panels (`fetch_theme_panel.py`) + `manifest.json` |
| `real-estate/` | Deal-implied cap rates and comps (context tier; `in_base_irr: false`) |
| `ira_download_manifest.json` | Last download log |

See `_system/frameworks/darwin_ira_research_plan.md`.

## Thematic context panels (`themes/`)

Broadly-ingested macro / industry indicators that explain why holdings' optionality reprices, consumed narrowly by tagged tickers.

- **Config:** `_system/scripts/theme_panel_config.json` (series + sources: FRED, Stooq, EIA, repo filings).
- **Tags:** `_system/portfolio/holdings_themes.json` (theme -> holdings).
- **Fetch:** `python _system/scripts/fetch_theme_panel.py` writes `themes/{id}.csv` (history) + `themes/manifest.json` (latest, YoY, direction, staleness). Offline-safe: cached history is kept on network failure.
- **Apply:** `python _system/scripts/apply_context_overlay.py` injects a `context_overlay` block into each tagged ticker's `valuation.json` and a `research/evidence/thematic_context_{date}.md` snippet.
- **Hard rule:** context only. Indicators carry `in_base_irr: false`; tailwinds never auto-inflate Lawrence base IRR. Human sets `in_base_irr: true` under **[HUMAN REVIEW]** to promote.
- First theme: `ai_power_land` (AI compute -> power demand -> grid/water constraint -> scarce Permian surface), tagged to TPL, LB, WBI, APLD, BWEL.
- Optional `EIA_API_KEY` enriches Permian production series; absent, that series degrades to null gracefully.
