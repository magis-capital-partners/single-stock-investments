# ABT — Cross-Check: Third-Party Sources

**Date:** 2026-07-21
**Agent:** Marvin (contract backfill refresh)
**Marvin dive:** `ABT/research/deep_dive_2026-07-21.md`
**Source inventory:** `ABT/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin floor **12.24%** per year (compounder; stance **watch**) from primary filings and `valuation.json`. Proof-first component schedule base **~$92.02/sh** vs **~$94.4** price. No third-party sources indexed; filings-only stance. **[HUMAN REVIEW]** for approved-source numeric blend.

**Synthesis (best estimate):** Marvin **12.24%** base · stance **watch**; external sources adjust conviction on catalyst timing, not primary IRR without human OK.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Base return anchor | **12.24%** per year | Qualitative support only | `ABT/research/deep_dive_2026-07-21.md` |
| Component economic value | **~$92.02/sh** base sum | No external anchor | `ABT/research/evidence_reconciliation_2026-07-21.md` |
| Archetype / stance | **compounder** · **watch** | See indexed sources | `valuation.json` |
| Normalization | FY2024 net income inflated by one-time items; base uses operating cash flow | Cross-check vs posts | Marvin |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | **12.24%** (Lawrence / scenarios) | No single approved IRR unless promoted | Marvin **70%** numeric; external **30%** catalyst timing |
| Third party | Filing-first | Context tier only | No numeric upgrade without human OK |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$4.23/sh** owner cash; **$92.02/sh** component sum | **12.24%** | **watch** |
| External (combined) | Narrative / catalyst | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | **12.24%** | **watch** |

**Weights:** Marvin **70%** on numbers; indexed third party **30%** on catalyst timing and narrative (approved Substacks/HK context only in qualitative layer until human promotes).

**Returns statement (blended):** We expect **12.24%** per year at today's price on the Marvin base case; third-party sources may raise or lower conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## Primary sources cited

1. `ABT/research/deep_dive_2026-07-21.md`
2. `ABT/research/valuation.json`
3. `ABT/research/evidence_reconciliation_2026-07-21.md`
4. `ABT/third-party-analyses/source_inventory_2026-07-10.md`
