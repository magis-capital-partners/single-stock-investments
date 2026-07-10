# AES — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `AES/research/deep_dive_2026-07-10.md`
**Source inventory:** `AES/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved or pending third-party research PDFs are indexed for AES as of this scan. Marvin stance rests on **primary SEC filings** (10-K FY2025, Q1 2026 10-Q, March 2026 merger 8-K, June 2026 fairness-opinion proxy materials). Fairness opinion ranges from J.P. Morgan (**$11.31–$16.39** per share) are cited as **filing context only**, not an approved external IRR input.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary SEC filings | 10-K, 10-Q, 8-K, 424B5, DEF 14A | filing | Marvin floor |
| J.P. Morgan fairness range (proxy) | Fairness opinion excerpt | context | Cross-check merger price vs SOTP |
| Third-party inventory | `source_inventory_2026-07-10.md` | empty | No Substacks / HK / notes |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Merger price | **$15.00** cash per share | JPM range includes $15.00 | `8-K_20260302`; `8-K_20260612` fairness materials |
| Backlog scale | **12.0 GW** contracted, not operating | n/a | `10-K_20260302` |
| Closing timeline | Late 2026 / early 2027 | n/a | `8-K_20260302` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Standalone value | Event path primary; normalized owner cash [Assumption] | JPM SOTP **$11.31–$16.39** | No blend — context only until human promotes source |
| Return horizon | ~9-month merger arb | n/a | Lawrence yield_curve base |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (merger arb) | **$15.00** cash payoff | ~**7%** annualized over ~0.75 years | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Merger consideration** | **~7%** annualized base | **watch** |

**Weights:** 100% Marvin floor — no approved third-party inputs.

**Returns statement (blended):** With no approved external sources, the blended best estimate equals Marvin's merger-arbitrage base of about **7%** per year — below the **~15%** bar.

## [HUMAN REVIEW]

- [ ] Promote any sell-side or infrastructure fund letters on AES/GIP deal if added to inventory
- [ ] Decide whether J.P. Morgan fairness range may inform break-price sensitivity (context vs base IRR)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AES third-party cross-check 2026-07-10: filings only; JPM fairness range **$11.31–$16.39** cited as context, not in base IRR.

## Primary sources cited

1. `AES/research/deep_dive_2026-07-10.md`
2. `AES/investor-documents/sec-edgar/8-K_20260302_rpt20260301_acc0001193125_26_084157.htm`
3. `AES/investor-documents/sec-edgar/8-K_20260612_rpt20260612_acc0001140361_26_025084.htm`
4. `AES/investor-documents/sec-edgar/10-K_20260302_rpt20251231_acc0000874761_26_000063.htm`
5. `AES/third-party-analyses/source_inventory_2026-07-10.md`
