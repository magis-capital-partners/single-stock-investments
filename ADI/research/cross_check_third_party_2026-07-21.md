# ADI — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin (contract backfill)  
**Marvin dive:** `ADI/research/deep_dive_2026-07-21.md`  
**Source inventory:** `ADI/third-party-analyses/source_inventory_2026-07-21.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for ADI as of 2026-07-21. Marvin stance rests on **primary filings only** (FY2025 10-K, Q2 FY2026 10-Q). Institutional SC 13G filings in `third-party-analyses/activist_reports/` are **context tier** only and do not enter base IRR.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| ID | Source | Path | Status | Use |
|----|--------|------|--------|-----|
| (none approved) | Primary filings only | `ADI/investor-documents/sec-edgar/` | primary | Base IRR anchor |
| context | SC 13G institutional filings | `ADI/third-party-analyses/activist_reports/long/` | context | Ownership history only |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue recovery | Revenue **$11.0B**, up from **$9.4B** FY2024 | No external cross-check | `10-K_20251125` |
| Free cash flow strength | FCF **$4.28B** (**$8.61/sh**) | No external cross-check | Same 10-K |
| Leverage from Maxim deal | Net debt **~$6.1B** | No external cross-check | Same 10-K balance sheet |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| AI/data-center option sizing | Base **+$18/sh** milestone band | No external view | Marvin judgment only; **[PENDING APPROVAL]** if sell-side added |
| Cycle reserve | Base **−$20/sh** | No external view | Filing-locked downside reserve |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (proof sum) | **$209.96/sh** base components | Mechanical synthesis in Phase 3 | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$209.96/sh** (Marvin only) | Pending mechanical refresh | **watch** |

**Weights:** 100% Marvin primary filings; no approved third-party sources.

**Returns statement (blended):** At about **$372** per share, proof-first component base **~$210/sh** implies the market prices analog moat and AI mix beyond conservative filing-locked components; final base annual return computed in Phase 3.

## [HUMAN REVIEW]

- [ ] Promote any third-party source to `third_party_sources.md` before including in base IRR
- [ ] Re-run `scan_third_party_sources.py ADI --with-hk` when Substacks or HK material is added

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ADI: third-party cross-check 2026-07-21; primary filings only; proof sum base **~$210/sh** vs **~$372** price.

## Primary sources cited

1. `ADI/investor-documents/sec-edgar/10-K_20251125_rpt20251101_acc0000006281_25_000153.htm`
2. `ADI/investor-documents/sec-edgar/10-Q_20260520_rpt20260502_acc0000006281_26_000052.htm`
3. `ADI/research/evidence_reconciliation_2026-07-21.md`
4. `ADI/third-party-analyses/source_inventory_2026-07-21.md`
