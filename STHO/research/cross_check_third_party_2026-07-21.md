# STHO — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin (contract backfill refresh)  
**Marvin dive:** `STHO/research/deep_dive_2026-07-21.md`  
**Source inventory:** `STHO/third-party-analyses/source_inventory_2026-07-20.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No sources are in the approved registry for STHO. McIntyre Partnerships Q1 2026 remains the only named external reference (**[PENDING APPROVAL]**). This refresh adds filing-backed component calculation proofs and corrects prior cash/debt arithmetic; it does not change the third-party inventory. Marvin's component base sum is now **~$18.10 per share** (proof-derived) vs price **~$9.24** (2026-07-20 market inputs from cloud refresh). McIntyre's repurchase optimism remains context only.

**Synthesis:** 100% Marvin proof-backed component schedule for base value; McIntyre not blended into base IRR.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| mcintyre-q1-26 | McIntyre Partnerships Q1 2026 Letter | `_system/reference/superinvestor-letters/2026Q1/McIntyre_Partnerships_Q1_2026_Letter.txt` | **[PENDING APPROVAL]** | Context — repurchase pace, net cash |

## Agreements (facts)

| Topic | Marvin (filings + proofs) | External | Source |
|-------|---------------------------|----------|--------|
| Repurchases active | Q1 2026 ~0.2M shares for $2.0M | ~10% of shares over 12 months | 8-K 2026-05-08; McIntyre letter |
| JV / mezzanine exit | March 27, 2026 Asbury mezz repaid; venture deconsolidated | Full repayment seller-financed JV | 8-K 2026-04-01; McIntyre letter |
| Book vs price gap | Q1 equity ~$19.88/sh; component base ~$18.10/sh | Large position; expects accelerated returns | 10-Q Q1 2026; McIntyre letter |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Value method | Seven-component proof schedule (SAFE, legacy, Magnolia/Asbury, cash, debt, fees, option) | Not quantified at component level | Marvin only in base |
| Net cash definition | Cash $62.1M less debt $207.0M at Q1 | "Net cash position" post-JV | Definitions differ; Marvin uses consolidated balance sheet |
| Stance | **watch** (related-party mgmt) | Constructive large position | External does not override gate |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin component base | **$18.10/sh** proof sum | **~14%** per year at $9.24 over 5yr (contract) | watch |
| External (McIntyre) | Accelerated repurchases | Not quantified | accumulate (external only) |
| **Blended best estimate** | **$18.10/sh base component value** | Contract annualized return at price | **watch** (Marvin gate) |

**Weights:** 100% Marvin proof-backed component schedule; McIntyre context only until promoted in `third_party_sources.md`.

## [HUMAN REVIEW]

- Promote McIntyre Q1 2026 to approved registry if human accepts context tier for repurchase narrative.
- Confirm SAFE high-case rate path is acceptable as sensitivity only.

## [PROPOSED MEMORY]

- None promoted this pass; see `_system/memory/daily/2026-07-21.md`.
