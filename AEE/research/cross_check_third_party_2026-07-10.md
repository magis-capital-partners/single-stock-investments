# AEE — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `AEE/research/deep_dive_2026-07-10.md`
**Source inventory:** `AEE/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No third-party sources are indexed for Ameren as of 2026-07-10 (`third-party-analyses/source_inventory_2026-07-10.md`). Marvin stance rests on **primary SEC filings only** (FY2025 10-K, Q1 2026 10-Q, 2026 proxy). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or sell-side notes are added to the folder.

**Synthesis (best estimate):** Marvin floor only. Base IRR ~7% per year on normalized regulated earnings power at today's price, below the **~15%** Lawrence bar. No external blend applied.

## Sources in scope

| ID | Source | Type | Status | Reviewed? |
|----|--------|------|--------|-----------|
| — | Primary filings only | SEC 10-K / 10-Q / DEF 14A | filing | Yes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 EPS | $5.35 diluted | n/a | `10-K_20260218_rpt20251231` |
| Capex plan 2026-2030 | $30.5-33.1B | n/a | 10-K Liquidity section |
| Dividend | $3.00 annual (Feb 2026) | n/a | 10-K |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash start | $5.10/sh normalized EPS | n/a | Filings only |
| Stance | watch (<15% IRR) | n/a | No external view to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $5.10/sh normalized earnings power | ~7% / 10yr | watch |
| External (combined) | n/a | n/a | n/a |
| **Blended best estimate** | **$5.10/sh** | **~7% / 10yr** | **watch** |

**Weights:** 100% Marvin floor (no approved or pending third-party analyses indexed).

**Returns statement (blended):** At today's price, Marvin expects about **7% per year** over ten years on normalized regulated earnings; no external sources adjust that estimate.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AEE: third-party cross-check 2026-07-10

## Primary sources cited

1. `AEE/research/deep_dive_2026-07-10.md`
2. `AEE/third-party-analyses/source_inventory_2026-07-10.md`
