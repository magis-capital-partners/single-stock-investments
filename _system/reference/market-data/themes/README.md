# Thematic indicator panels

Broadly-ingested macro / industry context that explains *why* holdings' optionality reprices. Consumed narrowly by tagged tickers only.

## Files

| Path | Contents |
|------|----------|
| `manifest.json` | Latest value, YoY, direction, staleness per series, grouped by theme |
| `{series_id}.csv` | Append-only history (`date,value`) per indicator |

## Pipeline

```bash
python _system/scripts/fetch_theme_panel.py            # refresh all themes
python _system/scripts/apply_context_overlay.py        # inject context_overlay into tagged valuation.json
```

- **Config:** `_system/scripts/theme_panel_config.json`
- **Tags:** `_system/portfolio/holdings_themes.json`
- **Sources:** FRED (rates, credit, gas, electricity, WTI), Stooq (daily closes), EIA (Permian production; needs `EIA_API_KEY`), and repo filings (hyperscaler capex from `ai_overlay` in `valuation.json`).

## Rules

- **Context only.** Every indicator carries `in_base_irr: false`. Tailwinds inform stance and overlay sizing; they never auto-inflate Lawrence base IRR.
- Promotion to base case requires a human to set `in_base_irr: true` (preserved across refreshes) under **[HUMAN REVIEW]**.
- Offline-safe: on network failure, cached CSV history is kept and the last known value is reused with an error note.
- No fabricated numbers: the hyperscaler capex series is derived from filing-cited `ai_overlay` blocks in each hyperscaler's `valuation.json`.

## Themes

| Theme | Chain | Tagged holdings |
|-------|-------|-----------------|
| `ai_power_land` | AI compute -> power demand -> grid/water constraint -> scarce Permian surface / hosting | TPL, LB, WBI, APLD, BWEL |

See `_system/frameworks/optionality_valuation.md` § **Thematic context layer**.
