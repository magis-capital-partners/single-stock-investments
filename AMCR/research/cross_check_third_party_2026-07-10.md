# AMCR — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `AMCR/research/deep_dive_2026-07-10.md`
**Source inventory:** `AMCR/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No third-party sources are indexed for AMCR as of 2026-07-10. Marvin stance rests on **primary filings only** (FY2025 10-K, Q3 FY2026 10-Q, merger 8-Ks). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base IRR and **watch** stance come from normalized post-merger owner cash in `valuation.json`.

## Sources in scope

| ID | Source | Type | Status | Reviewed |
|----|--------|------|--------|----------|
| — | Primary SEC filings | filing | n/a | yes |
| — | Third-party inventory empty | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Berry merger closed 2025-04-30 | Yes; 7.25 exchange ratio | — | `8-K_20250430_*` |
| FY2025 net sales $15.0B | Yes | — | FY2025 10-K |
| Pro forma revenue ~$23.2B | Yes | — | 10-K acquisition note |
| Long-term debt $13.8B post-merger | Yes | — | FY2025 10-K |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash normalization | $0.48/sh mid-point [Assumption] | — | No external view to blend |
| Stance | watch (<15% base IRR) | — | Filings-only gate |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | ~$0.48/sh normalized owner cash | ~8% base (7-yr model) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor** | **~8% base** | **watch** |

**Weights:** 100% Marvin (no approved external sources).

**Returns statement (blended):** At today's price, normalized owner cash supports roughly **8% per year** in the base case — below accumulate hurdle; **watch** until synergy proof or better price.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AMCR: third-party cross-check 2026-07-10

## Primary sources cited

1. `AMCR/research/deep_dive_2026-07-10.md`
2. `AMCR/third-party-analyses/source_inventory_2026-07-10.md`
