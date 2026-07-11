# XEL — Cross-Check: Third-Party Sources

**Date:** 2026-07-11  
**Agent:** Marvin  
**Marvin dive:** `XEL/research/deep_dive_2026-07-11.md`  
**Source inventory:** `XEL/third-party-analyses/source_inventory_2026-07-11.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for XEL as of this scan. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q, DEF 14A 2026). No new SEC or IR documents since 2026-07-10; narrative carries prior filing set. Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Material to base IRR? |
|--------|------|--------|----------------------|
| SEC filings (10-K, 10-Q, proxy) | Primary | reviewed | yes (sole input) |
| Third-party inventory | scan | empty | no |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 ongoing EPS | $3.80/sh | n/a | 10-K FY2025 Non-GAAP reconciliation |
| Base capex 2026-2030 | $60B | n/a | 10-K capital forecast table |
| Marshall wildfire charge | $287M (PSCo, Q3 2025) | n/a | 10-K Non-GAAP table |
| 2026 ongoing EPS guidance | $4.04-$4.16 | n/a | 10-K earnings guidance |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner-cash anchor | Ongoing EPS $3.80 (ex-wildfire) | n/a | Filings-only; GAAP $3.42 not used in base |
| Stance | watch (~7.84% synthesis at ~$80) | n/a | No external view to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $3.80/sh ongoing EPS | ~7.84% / 7yr | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$3.80/sh** | **~7.84% / 7yr** | **watch** |

**Weights:** 100% Marvin floor (no approved external sources).

**Returns statement (blended):** At ~$80 per share, Marvin filings-only base case implies roughly **7.84% per year** over seven years on **$3.80** ongoing owner cash; stance **watch**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] XEL third-party cross-check 2026-07-11: filings-only floor; no indexed external sources.

## Primary sources cited

1. `XEL/investor-documents/sec-edgar/10-K_20260225_rpt20251231_acc0000072903_26_000009.htm`
2. `XEL/investor-documents/sec-edgar/10-Q_20260430_rpt20260331_acc0000072903_26_000073.htm`
3. `XEL/research/deep_dive_2026-07-11.md`
4. `XEL/third-party-analyses/source_inventory_2026-07-11.md`
