# ACN — Cross-Check: Third-Party Sources

**Date:** 2026-07-10
**Agent:** Marvin
**Marvin dive:** `ACN/research/deep_dive_2026-07-10.md`
**Source inventory:** `ACN/third-party-analyses/source_inventory_2026-07-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for ACN as of this scan (`source_inventory_2026-07-10.md` lists zero Substacks, fund letters, or HK vault matches). Marvin stance rests on **primary filings only** (10-K FY2025, 10-Q Q2 FY2026, DEF 14A). Re-run `scan_third_party_sources.py ACN --with-hk` when external material is added.

**Synthesis:** Marvin floor only; no external blend. Lawrence base **26.6%** per year at ~$139 on FY2025 FCF/sh **$17.19**.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary SEC filings | 10-K, 10-Q, DEF 14A | in workspace | Base IRR inputs |
| Third-party | — | none indexed | — |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 scale | Revenue $69.7B; OCF $11.47B | — | 10-K FY2025 |
| AI positioning | $3B Gen AI investment since 2023 | — | 10-K Item 1 |
| Bookings trend | FY2025 −1% LC; Q2 FY2026 +1% LC | — | 10-K; 10-Q |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| FCF sustainability | Uses FY2025 OCF-derived FCF/sh $17.19 | — | No external view to blend |
| AI disruption | Partial dhando; bear = low growth not FCF collapse | — | Pending sell-side / substack views |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | FCF/sh $17.19 (FY2025) | 26.6% / 7yr synthesis | accumulate |
| External (combined) | — | — | — |
| **Blended best estimate** | **FY2025 filing FCF base** | **26.6%** | **accumulate** |

**Weights:** 100% Marvin (no approved external sources per `third_party_sources.md`).

**Returns statement (blended):** At ~$139, Marvin filing-based synthesis implies **26.6%** per year; no external adjustment until approved sources indexed.

## [HUMAN REVIEW]

- [x] Confirmed zero third-party sources in inventory
- [ ] Re-scan when Substacks or fund letters added for ACN
- [ ] If external views haircut FCF for AI, update `valuation.json` estimates.external[] after human approval

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] ACN: third-party cross-check 2026-07-10 — Marvin-only; no external blend.

## Primary sources cited

1. `ACN/investor-documents/sec-edgar/10-K_20251010_rpt20250831_acc0001467373_25_000217.htm`
2. `ACN/investor-documents/sec-edgar/10-Q_20260319_rpt20260228_acc0001467373_26_000014.htm`
3. `ACN/research/valuation.json`
4. `ACN/third-party-analyses/source_inventory_2026-07-10.md`
