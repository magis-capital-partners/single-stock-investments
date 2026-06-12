# STHO — Cross-Check: Third-Party Sources

**Date:** 2026-06-12
**Agent:** Marvin
**Marvin dive:** `STHO/research/deep_dive_2026-06-12.md`
**Source inventory:** `STHO/third-party-analyses/source_inventory_2026-06-12.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No approved third-party sources are indexed for Star Holdings as of 2026-06-12. Marvin stance rests on **primary SEC filings**. One **context-tier** fund letter (McIntyre Partnerships Q1 2026) mentions STHO as a large holding, net cash after a JV repayment, and ~10% share repurchases over twelve months; it is **not** in `third_party_sources.md` and does not enter base IRR.

**Synthesis:** Marvin floor only; McIntyre observations are directional context for liquidation pace, not blended into `valuation.json` base.

## Sources in scope

| ID | Title | Path | Status | Reviewed |
|----|-------|------|--------|----------|
| — | Primary filings | `STHO/investor-documents/sec-edgar/` | filing | Yes |
| ctx-mcintyre-q1-26 | McIntyre Partnerships Q1 2026 letter | `_system/reference/superinvestor-letters/2026Q1/McIntyre_Partnerships_Q1_2026_Letter.txt` | context | Yes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Wind-down mandate | Monetize legacy assets; no material new investments | McIntyre expects accelerated capital returns post-JV exit | 10-K; McIntyre letter |
| Repurchases below book | Q1 2026 avg ~$8.45 on ~0.2M shares | ~10% of shares repurchased over 12 months | 8-K exhibit; McIntyre letter |
| SAFE stake size | ~13.5M shares | — | 10-K spin-off note |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Liquidation pace | 4-year base to ~$19.50/sh | McIntyre: returns may accelerate now JV exited | External is context only; keep Marvin 4yr base until filing evidence of faster sales |
| Stance | accumulate (~20% yield curve) | McIntyre: second-largest position | No stance blend without approval |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Book ~$19.77/sh; SAFE floor ~$18/sh | ~20% / 4yr base | accumulate |
| External (combined) | Net cash narrative; faster return hope | n/a | context |
| **Blended best estimate** | **$19.50 payoff / 4yr** | **~20%** | **accumulate** |

**Weights:** 100% Marvin filings for base IRR; 0% external until human promotes McIntyre or other sources.

**Returns statement (blended):** Base **~20% per year** on four-year liquidation to ~$19.50 from ~$9.22; external letter does not change the mechanical base.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] STHO: third-party cross-check 2026-06-12

## Primary sources cited

1. `STHO/research/deep_dive_2026-06-12.md`
2. `STHO/third-party-analyses/source_inventory_2026-06-12.md`
