# AMAT — Cross-Check: Third-Party Sources

**Date:** 2026-07-10  
**Agent:** Marvin  
**Marvin dive:** `AMAT/research/deep_dive_2026-07-10.md`  
**Source inventory:** `AMAT/third-party-analyses/source_inventory_2026-07-10.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for AMAT as of this scan (`source_inventory_2026-07-10.md` lists zero entries). Marvin stance rests on **primary SEC filings only** (FY2025 10-K, Q2 FY2026 10-Q, FY2026 proxy). Insights archive references (Crescat, Horizon Kinetics commentary mentioning AMAT in AI/WFE themes) are **not approved** per `third_party_sources.md` and are cited here as **context tier only**, not in base IRR.

**Synthesis:** Marvin floor only; no external blend. Re-run `scan_third_party_sources.py AMAT --with-hk` when Substacks or fund letters are added.

## Sources in scope

| Source | Type | Status | Used in base IRR? |
|--------|------|--------|-------------------|
| Primary filings | 10-K, 10-Q, DEF 14A | Fact tier | Yes |
| Third-party inventory | Empty | n/a | No |
| Insights archive (Crescat/HK mentions) | Context | **[PENDING APPROVAL]** | No |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| WFE oligopoly position | Applied Materials is largest WFE supplier by revenue; two reportable segments SS + AGS | Context letters agree AMAT is core semi-cap equipment name | 10-K business description |
| AI demand driver | MD&A cites AI, HBM, advanced packaging as demand drivers | HK/Crescat archive mentions WFE supercycle thesis | 10-K MD&A FY2025 |

## Divergences (normalization / stance)

| Topic | Marvin floor | External (context) | Blend logic |
|-------|--------------|---------------------|-------------|
| WFE TAM growth | Base case **7%** years 1–5 owner-cash growth on FY2025 FCF | Some commentaries assume $300B WFE TAM in 3–4 years (vs ~$120B today) | External TAM bull case **not** in Lawrence base without filing-grounded share and timing |
| Valuation at spot | **-10.7%** Lawrence base IRR at **$588.66** on **$7.05/sh** FCF | Context sources often hold AMAT as quality AI infrastructure | Quality ≠ cheap; no blend adjustment without approved external model |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$7.05/sh** FY2025 FCF | **-10.7%** base / **-9.0%** synthesis (7yr) | watch |
| External (combined) | Not modeled | n/a | n/a |
| **Blended best estimate** | **$7.05/sh** filing FCF | **-9.0%** per year (Marvin-only) | **watch** |

**Weights:** 100% Marvin filings; zero approved third-party inputs.

**Returns statement (blended):** At **$588.66** with **$7.05/sh** starting owner cash, Marvin expects **-9.0%** per year over seven years on the total-synthesis path; no external views in base IRR.

## [HUMAN REVIEW]

- [ ] Promote any fund-letter or Substack source to `third_party_sources.md` before adding to `valuation.json` estimates
- [ ] Confirm whether WFE supercycle commentary (insights archive) warrants bull-scenario weight increase

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AMAT onboard deep dive 2026-07-10: FY2025 FCF **$7.05/sh**; **-9.0%** synthesis IRR at **$588.66**; watch

## Primary sources cited

1. `AMAT/investor-documents/sec-edgar/10-K_20251212_rpt20251026_acc0001628280_25_056742.htm`
2. `AMAT/investor-documents/sec-edgar/10-Q_20260521_rpt20260426_acc0001628280_26_037227.htm`
3. `AMAT/research/valuation.json`
4. `AMAT/third-party-analyses/source_inventory_2026-07-10.md`
