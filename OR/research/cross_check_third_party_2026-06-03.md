# OR — Cross-Check: Third-Party Sources

**Date:** 2026-06-03
**Agent:** Marvin
**Marvin dive:** `OR/research/deep_dive_2026-06-03.md`
**Source inventory:** `OR/third-party-analyses/source_inventory_2026-06-03.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No third-party sources are indexed for this ticker as of this scan. Marvin stance rests on **primary filings only** (40-F exhibits 99.1–99.3, MD&A March 2026). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base Lawrence path uses FY2025 operating cash flow per share ($1.31) with 2030 GEO growth mechanism from MD&A; dividend yield ~6% supports partial dhando floor.

## Sources in scope

| Source | Type | Status | Reviewed |
|--------|------|--------|----------|
| Primary 40-F / MD&A | SEC filing | primary | Yes |
| (none external) | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 GEOs | 80,775 | — | `40-F_20260330_exhibit99-3.htm` |
| Record OCF | $245.6M | — | Same |
| 2030 GEO outlook | 120–135k | — | Same, 5-year outlook section |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash starting point | OCF $1.31/sh | n/a | No external view |
| Development upside | Probability-weighted overlay | n/a | Not in base IRR without approval |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $1.31/sh OCF start | Lawrence 7yr (pending) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **pending** | **watch** |

**Weights:** 100% Marvin primary filings; no approved third party.

**Returns statement (blended):** Same as Marvin base case pending mechanical refresh; no external blend.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] OR: third-party cross-check 2026-06-03

## Primary sources cited

1. `OR/research/deep_dive_2026-06-03.md`
2. `OR/third-party-analyses/source_inventory_2026-06-03.md`
