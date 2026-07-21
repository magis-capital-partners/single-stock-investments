# ADM — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin  
**Marvin dive:** `ADM/research/deep_dive_2026-07-21.md`  
**Source inventory:** `ADM/third-party-analyses/source_inventory_2026-07-21.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for ADM as of 2026-07-21. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q, Jan 2026 SEC settlement 8-K). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `ADM/investor-documents/sec-edgar/` | primary | 10-K FY2025, 10-Q Q1 2026, 8-K SEC settlement |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Revenue decline | FY2025 revenue $80.3B vs $85.5B FY2024 | — | FY2025 10-K |
| OCF recovery | FY2025 OCF $5.45B vs $2.79B FY2024 | — | FY2025 10-K |
| SEC settlement | $40M civil penalty; investigations closed | — | 8-K 2026-01-28 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Component sum base **~$68.58/sh** | Lawrence base **~12%** per year (7yr owner-cash path) | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **~$68.58/sh** (component proof sum) | **~12%** Lawrence synthesis vs **~$86** price | **watch** |

**Weights:** 100% Marvin primary filings; no approved third party in base IRR.

**Returns statement (blended):** At **~$86** per share, filing-based owner cash implies roughly **12%** per year over seven years on the consolidated path, but proof-first component sum (**~$69/sh**) sits below price; we propose **watch** pending mid-cycle normalization and leverage review.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## Primary sources cited

1. `ADM/investor-documents/sec-edgar/10-K_20260217_rpt20251231_acc0000007084_26_000011.htm`
2. `ADM/investor-documents/sec-edgar/10-Q_20260505_rpt20260331_acc0000007084_26_000023.htm`
3. `ADM/investor-documents/sec-edgar/8-K_20260128_rpt20260127_acc0001193125_26_025560.htm`
4. `ADM/research/evidence_reconciliation_2026-07-21.md`
