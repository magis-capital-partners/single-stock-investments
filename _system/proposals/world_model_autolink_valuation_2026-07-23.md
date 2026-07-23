# Plan: Auto-link World Model → agent valuation & deep dives

**Status:** implemented (2026-07-23).  
**Hard rule preserved:** World Model stays **context-first**. No silent rewrite of Lawrence `inputs` / `scenarios` / `implied_return`.

## Goal

Give Marvin (and monthly CI) a mechanical path from World Model state → deep-dive / valuation artifacts, with **explicit human promotion** before anything touches base IRR.

## Industry scope (hold / researched book)

| Kind | Count | Nodes |
|------|------:|-------|
| Thesis | 11 | `ai_power`, `water_surface`, `hyperscaler_cloud`, `gold_royalty`, `exchange_markets`, `market_data_indices`, `timber_land`, `btc_mining_power`, `energy_royalty`, `pharma_royalty`, `nuclear_firm_power` |
| Horizon | 2 | `agi`, `robotaxi` |
| **Total** | **13** | |

Not the full ~700-name registry — only hold/core + KPI + researched theme clusters. Taxonomy: `_system/reference/world_model/README.md`.

## Staged auto-link

| Phase | Status | Mechanism |
|------:|--------|-----------|
| 0 Visibility | done | Strip + README industry counts |
| 1 Deep-dive inject | **live** | `refresh_deep_dive_v2.py` → `#### World Model context` |
| 2 valuation.json | **live** | `apply_world_model_context.py` → `world_model_context` (`in_base_irr: false`) |
| 3 Soft gates | **live** | `--queue-reviews` → `_system/reviews/pending/world_model_review_*` |
| 4 Human promotion | **live (gated)** | `_system/reviews/templates/world_model_promote.md` |
| 5 Agent tooling | **live** | Runbook pre-check; `marvin_cloud_refresh.py`; monthly CI |

## Commands

```bash
python _system/scripts/build_world_model_snapshot.py
python _system/scripts/apply_world_model_context.py ICE --write --queue-reviews
python _system/scripts/apply_world_model_context.py --all --write --queue-reviews
python _system/scripts/refresh_deep_dive_v2.py ICE
python _system/scripts/ci_rebuild_profile.py world-model-weekly
```

## Explicit non-goals

- Nightly full rebuild of World Model (stays weekly on weekends).
- Treating AGI/robotaxi quotes as FCF or exit multiples.
- Auto-raising growth rates from hyperscaler capex or horizon convergence.
- Cloning a 20-year Courtenay daily stack.
