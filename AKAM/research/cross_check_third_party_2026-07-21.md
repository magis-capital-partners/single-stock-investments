# AKAM — Cross-Check: Third-Party Sources

**Date:** 2026-07-21
**Agent:** Marvin (contract backfill refresh)
**Marvin dive:** `AKAM/research/deep_dive_2026-07-21.md`
**Source inventory:** `AKAM/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin floor **15.83%** per year (platform; stance **hold**) from primary filings and `valuation.json`. Proof-first component schedule base **~$125/sh** vs **~$130** price. No third-party sources indexed; filings-only stance. **[HUMAN REVIEW]** for approved-source numeric blend.

**Synthesis (best estimate):** Marvin **15.83%** base · stance **hold**; external sources adjust conviction on catalyst timing, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Base return anchor | **15.83%** per year | Qualitative support only | `AKAM/research/deep_dive_2026-07-21.md` |
| Component sum base | **~$125/sh** | No external anchor | `valuation.json` component_valuation |
| Archetype / stance | **platform** · **hold** | See indexed sources | `valuation.json` |
| Normalization | FY2025 reported free cash flow; Q1 2026 operating margin compressed on compute build-out | Cross-check vs posts | Marvin |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **15.83%** (Lawrence / scenarios) | No single approved IRR unless promoted | Marvin **70%** numeric; external **30%** catalyst timing |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Component sum **~$125/sh** | **15.83%** | **hold** |
| External (combined) | Narrative / catalyst | No change to base % | **hold** (conviction) |
| **Blended best estimate** | **Filing anchor** | **15.83%** | **hold** |

**Weights:** Marvin **70%** on numbers; indexed third party **30%** on catalyst timing and narrative (approved Substacks/HK context only in qualitative layer until human promotes).

**Returns statement (blended):** We expect **15.83%** per year at today's price on the Marvin base case; third-party sources may raise or lower conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AKAM: contract backfill 2026-07-21 — proof-first component schedule base ~$125/sh vs ~$130 price; convertible debt ~$22/sh net claim remains widest capital-structure band.

## Primary sources cited

1. `AKAM/research/deep_dive_2026-07-21.md`
2. `AKAM/research/valuation.json`
3. `AKAM/research/evidence_reconciliation_2026-07-21.md`
4. `AKAM/third-party-analyses/source_inventory_2026-07-10.md`
