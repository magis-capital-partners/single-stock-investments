# ASTS — Cross-Check: Third-Party Sources

**Date:** 2026-07-17  
**Agent:** Marvin  
**Marvin dive:** `ASTS/research/deep_dive_2026-07-17.md`  
**Source inventory:** `ASTS/third-party-analyses/source_inventory_2026-07-17.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for ASTS as of 2026-07-17. Marvin stance rests on **primary SEC filings only** (FY2025 10-K, Q1 2026 10-Q, proxy). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base scenario annual return roughly **-8%** at **$57.23** on partial commercial ramp assumptions in `valuation.json`.

## Sources in scope

| ID | Source | Type | Status | Reviewed |
|----|--------|------|--------|----------|
| — | Primary filings only | SEC | n/a | Yes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| — | — | — | No external sources |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | — |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | -$3.42/sh owner cash FY2025 | Negative on Lawrence path | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Scenario base ~$45/sh payoff yr7** | **~-8%/yr base scenario** | **watch** |

**Weights:** 100% Marvin filing floor; 0% external (none indexed).

**Returns statement (blended):** At **$57.23**, Marvin base scenario implies roughly **-8% per year** over seven years; no third-party views in base IRR.

## [HUMAN REVIEW]

- [x] Every **approved** source reviewed against filings (none indexed)
- [x] Every **pending** source cited with **[PENDING APPROVAL]** only (none)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added

## Primary sources cited

1. `ASTS/research/deep_dive_2026-07-17.md`
2. `ASTS/third-party-analyses/source_inventory_2026-07-17.md`
3. `ASTS/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0001780312_26_000006.htm`
4. `ASTS/investor-documents/sec-edgar/10-Q_20260511_rpt20260331_acc0001193125_26_216950.htm`
