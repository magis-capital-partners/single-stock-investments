# Insights tab upgrade (non-AI)

**Status:** Implemented 2026-06-09  
**Goal:** ~70–80% of Buyside Digest fund-page utility, zero runtime LLM cost.

## Architecture (unchanged)

```
Letter .txt → build_superinvestor_insights.py → superinvestor-letters/insights.json
                                                      ↓
                                              build_insights.py → dashboard/data/insights.json
                                                      ↓
                                              insights-viz.js (static render)
```

All enrichment is **deterministic, re-runnable, committed JSON**. UI reads pre-built data only.

## What we ship

| Feature | Source | Cost |
|---------|--------|------|
| Robust ticker extraction | Regex + known-universe match | 0 tokens |
| Ticker commentary snippets | Sentence around mention | 0 tokens |
| Theme tags + per-theme stance | Keyword map (expanded) | 0 tokens |
| Section heuristics (risks, catalysts, outlook) | Header/line parsing | 0 tokens |
| Lead summary | First substantive paragraphs | 0 tokens |
| Letter index table | Structured letter records | 0 tokens |
| Fund registry + drill-down | Grouped by `fund_id` | 0 tokens |
| "In our book" filter | Overlap vs `registry.json` | 0 tokens |
| Persona cross-links | `fund_persona_map` | 0 tokens |
| Per-ticker "who discusses" | `by_ticker` letter records | 0 tokens |

## Explicitly deferred (AI or external data)

- Executive summaries / meta gauges (BSD-style conviction scores)
- 13F buys/sells (needs SEC CIK map + fetch adapter)
- Manager bios from external sources
- Full industry classification on pitches

## Rebuild commands

```bash
python _system/scripts/build_superinvestor_insights.py
python _system/scripts/build_insights.py
python _system/scripts/build_dashboard_data.py
# or: make persona-fetch-letters && python _system/scripts/build_dashboard_data.py
```

## Data schema additions

### Letter record (`insights.json` letters[])

- `fund_id`, `lead_summary`, `risks[]`, `catalysts[]`, `macro_views[]`
- `positions[].commentary` — sentence snippet
- `themes[].stance` — per-theme (not letter-global)

### Dashboard payload (`dashboard/data/insights.json`)

- `letter_index[]` — flat table for UI
- `fund_profiles{}` — keyed by `fund_id`, letters grouped
- Enhanced `fund_registry[]` — themes, tickers, personas, `fund_id`

## Quality gates

1. No single-letter false tickers (`A`, `I`) unless in known universe
2. Theme `top_tickers` must be real symbols from letter text
3. Fund drill-down must link to GitHub extract path
4. Letter insights never set `in_base_irr: true`
