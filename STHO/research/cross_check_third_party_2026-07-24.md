# STHO — Cross-Check: Third-Party Sources

**Date:** 2026-07-24
**Agent:** Marvin (contract backfill — third-party inventory unchanged)
**Marvin dive:** `STHO/research/deep_dive_2026-07-24.md`
**Source inventory:** `STHO/third-party-analyses/source_inventory_2026-06-12.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No sources are in the approved registry for STHO. One **context-tier** reference exists in the workspace superinvestor letter library: McIntyre Partnerships Q1 2026, which discusses STHO as a top holding, net cash after a seller-financed JV repayment, and ~10% repurchases over twelve months. Marvin's filing-based floor shows Q1 2026 book ~$19.88 per share vs price ~$8.55. McIntyre's capital-return optimism is directionally consistent with loan repayments and deconsolidation in the March 2026 8-K but is **[PENDING APPROVAL]** and not blended into base IRR.

**Synthesis:** Marvin proof-backed component NAV (~$18.1/sh base sum) for contract; McIntyre cited as context pending human promotion. Base yield-curve return unchanged at **10.4%** per year pending mechanical refresh.

## Sources in scope

| ID | Title | Path | Status | Use |
|----|-------|------|--------|-----|
| mcintyre-q1-26 | McIntyre Partnerships Q1 2026 Letter | `_system/reference/superinvestor-letters/2026Q1/McIntyre_Partnerships_Q1_2026_Letter.txt` | **[PENDING APPROVAL]** | Context — repurchase pace, net cash |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Repurchases active | Q1 2026 ~0.2M shares for $2.0M; FY2025 ~$8M | ~10% of shares over 12 months | 8-K 2026-05-08; McIntyre letter |
| JV / mezzanine exit | March 27, 2026 Asbury mezz repaid; venture deconsolidated | Full repayment seller-financed JV; net cash | 8-K 2026-04-01 ex.99.1; McIntyre letter |
| Concentrated legacy assets | Asbury + Magnolia + SAFE dominate book | Large position; expects accelerated returns | 10-K FY2025; McIntyre letter |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Return horizon | 5yr base payoff $15/sh (75% book) | Implies faster capital return post-JV | McIntyre bull case not in base IRR |
| Stance | **watch** (related-party mgmt) | Large fund position; constructive | External does not override gate without approval |
| Net cash | $67M cash+restricted; $207M debt | "Net cash position" post-JV | Definitions differ; Marvin uses consolidated balance sheet |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Q1 book $19.88/sh; base $15/sh in 5yr | **10.4%** per year (base) | watch |
| External (McIntyre) | Accelerated repurchases | Not quantified | accumulate (external only) |
| **Blended best estimate** | **$15/sh base payoff** | **10.4%** per year | **watch** (Marvin gate) |

**Weights:** 100% Marvin floor for base IRR until McIntyre is promoted in `third_party_sources.md`.

**Returns statement (blended):** Base IRR remains **10.4%** per year on Marvin assumptions; McIntyre optimism is context only.

## [HUMAN REVIEW]

- [ ] Promote McIntyre letter to approved registry if desired
- [ ] Reconcile "net cash" wording with Q1 consolidated balance sheet
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] STHO cross-check 2026-06-12: McIntyre context only; Marvin base 10.4% yield-curve.

## Primary sources cited

1. `STHO/research/deep_dive_2026-06-12.md`
2. `STHO/third-party-analyses/source_inventory_2026-06-12.md`
3. `_system/reference/superinvestor-letters/2026Q1/McIntyre_Partnerships_Q1_2026_Letter.txt`
4. `STHO/investor-documents/sec-edgar/10-Q_20260508_rpt20260331_acc0001953366_26_000010.htm`
5. `STHO/investor-documents/sec-edgar/8-K_20260401_exhibit_stho-20260327xex99d1.htm_acc0001953366_26_000006.htm`
