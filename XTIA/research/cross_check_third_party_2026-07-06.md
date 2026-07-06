# XTIA — Cross-Check: Third-Party Sources

**Date:** 2026-07-06  
**Agent:** Marvin  
**Marvin dive:** `XTIA/research/deep_dive_2026-07-06.md`  
**Source inventory:** `XTIA/third-party-analyses/source_inventory_2026-07-06.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for XTIA as of 2026-07-06. Marvin stance rests on **primary SEC filings** (FY2025 10-K, Q1 2026 10-Q, merger and acquisition 8-Ks). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or sell-side notes are added.

**Synthesis:** Marvin floor only; no external blend. Base annual return and stance come from scenario build in `valuation.json`, not from external normalization.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `XTIA/investor-documents/sec-edgar/` | n/a | Business mechanics, capital structure |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue engine | Commercial drone distribution via Drone Nerds (83.4% stake) | n/a | `10-K_20260415_rpt20251231_acc0001213900_26_043785.htm` |
| Strategic pivot | Merger with Legacy XTI; Inpixon business discontinued | n/a | Same 10-K Item 1 |
| Q1 2026 revenue | $27.7M consolidated | n/a | `10-Q_20260514_rpt20260331_acc0001213900_26_056270.htm` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to reconcile |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Negative quarterly owner cash (~-$0.27/sh) | Scenario base ~9% per year over 5 years | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Scenario-weighted** | **See `valuation.json` implied_return** | **watch** |

**Weights:** 100% Marvin primary filings; no approved third party in base IRR.

**Returns statement (blended):** Pending mechanical refresh from `marvin_valuation.py`; executive summary matches base scenario annual return after pipeline run.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] XTIA: pivot from Inpixon to drone distribution (Drone Nerds, 83.4%); ADS division pre-revenue; Q1 2026 revenue $27.7M; warrant liability $64.9M; stance watch at ~$1.59.

## Primary sources cited

1. `XTIA/investor-documents/sec-edgar/10-K_20260415_rpt20251231_acc0001213900_26_043785.htm`
2. `XTIA/investor-documents/sec-edgar/10-Q_20260514_rpt20260331_acc0001213900_26_056270.htm`
3. `XTIA/third-party-analyses/source_inventory_2026-07-06.md`
