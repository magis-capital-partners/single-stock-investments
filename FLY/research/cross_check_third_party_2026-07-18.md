# FLY — Cross-Check: Third-Party Sources

**Date:** 2026-07-18  
**Agent:** Marvin  
**Marvin dive:** `FLY/research/deep_dive_2026-07-18.md`  
**Source inventory:** `FLY/third-party-analyses/source_inventory_2026-07-18.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for FLY as of this scan (`scan_third_party_sources.py FLY --with-hk --date 2026-07-18` returned zero matches). Marvin stance rests on **primary filings only** (10-K FY2025, 10-Q Q1 2026, 8-K series, proxy). Re-run the scan when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base Lawrence annual return **2.2%** at **$19.27** on normalized **$0.35/sh** owner cash.

## Sources in scope

| Source | Type | Status | Reviewed |
|--------|------|--------|----------|
| Primary SEC filings | 10-K, 10-Q, 8-K, DEF 14A | filing | Yes |
| Third-party inventory | — | none indexed | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue scale | FY2025 **$159.9M**; Q1 2026 **$80.9M** | — | 10-K FY2025; 10-Q Q1 2026 |
| Backlog | RPO **$652.6M**; **36.9%** within 12 months | — | 10-Q Q1 2026 |
| Q1 profitability | Operating loss **($95.7M)**; net loss **($96.7M)** | — | 10-Q Q1 2026 |
| Cash | **$326.2M** at Mar 31, 2026 vs **$793.0M** at Dec 31, 2025 | — | 10-Q Q1 2026 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash | **$0.35/sh** normalized (not raw OCF **$1.28/sh**) | — | Haircut for growth capex, SciTec integration, Q1 operating loss |
| Backlog vs IRR | RPO **$4.08/sh** context only | — | Not in Lawrence base without conversion proof |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$0.35/sh** normalized | **2.2%** per year (7yr base) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$0.35/sh** | **2.2%** per year | **watch** |

**Weights:** 100% Marvin filings (no approved third party).

**Returns statement (blended):** At **$19.27**, Marvin base case is **2.2%** per year over seven years on normalized owner cash of **$0.35** per share; pending sources are not in base annual return.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added later

## Primary sources cited

1. `FLY/research/deep_dive_2026-07-18.md`
2. `FLY/third-party-analyses/source_inventory_2026-07-18.md`
3. `FLY/investor-documents/sec-edgar/10-K_20260320_rpt20251231_acc0001193125_26_116309.htm`
4. `FLY/investor-documents/sec-edgar/10-Q_20260504_rpt20260331_acc0001860160_26_000009.htm`
