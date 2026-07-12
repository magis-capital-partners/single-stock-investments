# Darwin AI Ventures → Marvin/Darwin stack alignment

**Status:** Workstream A complete (2026-06-02)  
**Letter:** `_system/reference/quant-evolution/Darwin_AI_Investments_1Q26.pdf` (gitignored)  
**Extract:** `Darwin_AI_Investments_1Q26_extract.txt`  
**Mandate:** `_system/portfolio/darwin_mandate.json` → `source_overrides`

## Mapping table

| # | Source claim | Our implementation | Action |
|---|--------------|-------------------|--------|
| 1 | Adaptive neural strategies | Marvin autoencoder + latent PPO | replicate |
| 2 | RL with real-market constraints | Turnover in reward + mandate caps | replicate |
| 3 | Evolutionary / population search | GA + persisted `population.json` | replicate |
| 4 | Regime adaptation | `regime.py` (VIX/yields + falsifiers) | replicate |
| 5 | Concentrated book, low turnover | 8–12 names, semiannual, 10% cap | replicate |
| 6 | Proprietary weights | N/A | skip |

## Differentiator

Marvin (`valuation.json`, falsifiers, stance) is the **epistemic engine**. Darwin is the **allocation engine** and ML is a sanity check until OOS Sharpe clears gates.

## Covered-call arithmetic (Phase B)

Research overlay only — **not** Darwin AI Ventures proprietary NN.

| Symbol | Meaning |
|--------|---------|
| `tenor_days` | Call tenor (default 7) |
| `rolls_per_month` | ≈ 30.4 / tenor_days |
| `premium_monthly` | `(annual_yield/100) / (rolls_per_year) × (1 − bid_ask_haircut) × rolls_per_month` |
| `upside_cap` | From `otm_pct` with √rolls heuristic (see `covered_call.upside_cap_from_otm`) |
| Name-level | Premium × vol_scale; coverage × stance × liquidity bucket; regime mult on book coverage |
| Assignment | Flat `assignment_bps` haircut on covered sleeve |

Options marks (Phase D lab): cache-first — etf-dashboard overlaps free, champion-only live refresh with hard API caps (`refresh_darwin_options_cache.py`). Synthetic IV from realized vol when no chain.

## Rebuild

```bash
pip install -r _system/scripts/requirements-darwin.txt
python3 _system/scripts/download_ira_research.py --tier A
python3 _system/scripts/download_ira_research.py --tier B
python3 _system/scripts/darwin/refresh_darwin_options_cache.py --import-etf-only
python3 _system/scripts/build_darwin_portfolio.py
python3 _system/scripts/build_dashboard_data.py
```
