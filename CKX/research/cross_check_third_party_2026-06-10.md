# CKX — Cross-Check: Third-Party Sources

**Date:** 2026-06-10
**Agent:** Marvin
**Marvin dive:** `CKX/research/deep_dive_2026-06-10.md`
**Source inventory:** `CKX/third-party-analyses/source_inventory_2026-06-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for CKX as of this scan. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q, Nov-2025 land-sale 8-K, strategic-process 8-Ks). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base case uses filing-based cash floor (**~$8.78** per share), normalized operating cash flow (**~$0.22** per share), and illustrative acreage marks tied to the November 2025 **~$1,316/acre** transaction comp **[Assumption]**.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| (none) | Primary filings only | `CKX/investor-documents/sec-edgar/` | n/a | Marvin floor |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Land sale Nov-2025 | **6,548** acres for **$8,618,022** | — | `8-K_20251120` / 10-K Note 4 |
| Net acreage | **7,023** net acres in Louisiana | — | 10-K Item 2 |
| Cash position | **$18.0M** at 12/31/2025 | — | 10-K balance sheet |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to reconcile |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **~$0.22/sh** run-rate cash; **~$15.50/sh** dated payoff | **3.7%** / 7yr | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **3.7%** | **watch** |

**Weights:** 100% Marvin filings; no approved external sources.

**Returns statement (blended):** At **~$10.59**, we expect about **3.7%** per year over seven years on the Marvin dated-payoff base case; no third-party views are in the blend.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [x] Every **pending** source cited with **[PENDING APPROVAL]** only (n/a)
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material (not applicable)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] CKX: third-party cross-check 2026-06-10 — Marvin floor only; 0 indexed sources.

## Primary sources cited

1. `CKX/research/deep_dive_2026-06-10.md`
2. `CKX/third-party-analyses/source_inventory_2026-06-10.md`
3. `CKX/investor-documents/sec-edgar/10-K_20260331_rpt20251231_acc0001437749_26_010434.htm`
4. `CKX/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001437749_26_015951.htm`
