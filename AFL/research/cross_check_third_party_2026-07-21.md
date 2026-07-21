# AFL — Cross-Check: Third-Party Sources

**Date:** 2026-07-21
**Agent:** Marvin (contract backfill refresh)
**Marvin dive:** `AFL/research/deep_dive_2026-07-21.md`
**Source inventory:** `AFL/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin floor **8.03%** per year (compounder; stance **watch**) from primary filings and `valuation.json`. No third-party sources indexed; filings-only stance. **[HUMAN REVIEW]** for approved-source numeric blend.

**Synthesis (best estimate):** Marvin **8.03%** base · stance **watch**; external sources adjust conviction on catalyst timing, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Base return anchor | **7.93%** per year | Qualitative support only | `AFL/research/deep_dive_2026-07-21.md` |
| Archetype / stance | **compounder** · **watch** | See indexed sources | `valuation.json` |
| Normalization | FY2025 GAAP net income fell to $3.65B (EPS $6.82) from $5.44B on investment mark | Cross-check vs posts | Marvin |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **8.03%** (Lawrence / scenarios) | No single approved IRR unless promoted | Marvin **70%** numeric; external **30%** catalyst timing |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | See assumption ledger | **8.03%** | **watch** |
| External (combined) | Narrative / catalyst | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | **8.03%** | **watch** |

**Weights:** Marvin **70%** on numbers; indexed third party **30%** on catalyst timing and narrative (approved Substacks/HK context only in qualitative layer until human promotes).

**Returns statement (blended):** We expect **8.03%** per year at today's price on the Marvin base case; third-party sources may raise or lower conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AFL: third-party cross-check fill 2026-07-21 — Marvin ~8% unchanged; proof-first component sum **~$116/sh**

## Primary sources cited

1. `AFL/research/deep_dive_2026-07-21.md`
2. `AFL/research/valuation.json`
3. `AFL/third-party-analyses/source_inventory_2026-07-10.md`
