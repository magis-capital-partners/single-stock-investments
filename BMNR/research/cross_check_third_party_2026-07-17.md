# BMNR — Cross-Check: Third-Party Sources

**Date:** 2026-07-17  
**Agent:** Marvin  
**Marvin dive:** `BMNR/research/deep_dive_2026-07-17.md`  
**Source inventory:** `BMNR/third-party-analyses/source_inventory_2026-07-17.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for BMNR as of 2026-07-17. Marvin stance rests on **primary SEC filings only** (10-K FY2025, 10-Q Q3 FY2026, DEF 14A, July 2026 8-K). The July 16, 2026 Tom Lee presentation filed as Exhibit 99.1 is **company Reg FD material**, not an approved external research source.

**Synthesis:** Marvin floor only; no external blend. Base IRR and stance follow filing-based look-through ETH scenarios in `valuation.json`.

## Sources in scope

| Source | Type | Status | Reviewed |
|--------|------|--------|----------|
| (none indexed) | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| — | — | — | — |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | — |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (ETH look-through) | ~$18.76 per share ETH fair value at May 31, 2026 | Seven-year yield-curve scenarios in `valuation.json` | watch pending mechanical IRR |
| External (combined) | — | — | — |
| **Blended best estimate** | **Filing-based only** | **Mechanical refresh** | **watch** |

**Weights:** No approved third-party inputs; 100% primary filings.

**Returns statement (blended):** Pending `marvin_valuation.py --write`; no external views in base case.

## [HUMAN REVIEW]

- [ ] Re-run `scan_third_party_sources.py BMNR --with-hk` when Substacks or fund letters cover BMNR.
- [ ] Do not promote Tom Lee presentation or social media ETH targets into base IRR without human approval.

## Primary sources cited

1. `BMNR/research/deep_dive_2026-07-17.md`
2. `BMNR/third-party-analyses/source_inventory_2026-07-17.md`
3. `BMNR/investor-documents/sec-edgar/10-K_20251121_rpt20250831_acc0001493152_25_024679.htm`
4. `BMNR/investor-documents/sec-edgar/10-Q_20260714_rpt20260531_acc0001628280_26_048157.htm`
