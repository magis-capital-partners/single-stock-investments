# DB1.DE — Cross-Check: Third-Party Sources

**Date:** 2026-06-11
**Agent:** Marvin
**Marvin dive:** `DB1.DE/research/deep_dive_2026-06-11.md`
**Source inventory:** `DB1.DE/third-party-analyses/source_inventory_2026-06-11.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No third-party sources are indexed for this ticker as of this scan. Marvin stance rests on **primary filings only** (annual report 2025, Q1 2026 quarterly statement). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base case about **13%** per year at **€246** on **€12.52** FY2025 free cash flow per share.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| `investor-documents/ir-db1/annual_report_2025.pdf` | Primary filing | in repo | FY2025 segment and cash-flow anchor |
| `investor-documents/ir-db1/quarterly_statement_q1_2026.pdf` | Primary filing | in repo | Latest quarterly KPIs |
| Third-party inventory | — | empty | No approved or pending external IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 net revenue ex treasury | €5,189M (+9%) | n/a | `annual_report_2025.pdf` |
| Q1 2026 net revenue ex treasury | €1,434M (+12%) | n/a | `quarterly_statement_q1_2026.pdf` |
| Archetype | croupier | n/a | Stahl framework |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Starting owner cash | €12.52/sh FY2025 FCF | n/a | No external normalization to reconcile |
| Stance | watch (<15% base) | n/a | Filings-only gate |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | €12.52 FCF/sh FY2025 | ~13% base / 7yr | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **€12.52 FCF/sh** | **~13% base** | **watch** |

**Weights:** 100% Marvin floor (no approved third-party IRR).

**Returns statement (blended):** At about **€246** per share we expect about **13%** per year over 7 years on FY2025 free cash flow per share; no external views in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] DB1.DE: third-party cross-check 2026-06-11

## Primary sources cited

1. `DB1.DE/research/deep_dive_2026-06-11.md`
2. `DB1.DE/third-party-analyses/source_inventory_2026-06-11.md`
