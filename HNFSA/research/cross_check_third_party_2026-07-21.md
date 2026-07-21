# HNFSA — Cross-Check: Third-Party Sources

**Date:** 2026-07-21
**Agent:** Marvin (contract backfill refresh)
**Marvin dive:** `HNFSA/research/deep_dive_2026-07-21.md`
**Source inventory:** `HNFSA/third-party-analyses/source_inventory_2026-07-20.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin floor **3.9%** per year (optionality; stance **watch**) from primary SEC filings and `valuation.json`. Proof-first component base economic value **~$61.24/sh** vs price **~$55**. No approved third-party sources in base IRR; aggregator book and debt remain **[Assumption]** context only.

**Synthesis (best estimate):** Marvin **3.9%** base · stance **watch**; no external numeric blend until verified shareholder financials.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | — | — | — | Primary filings only |
| aggregator | Yahoo / Stockanalysis snapshots | Web context | **[Assumption] / pending** | Context only; not in base IRR |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Business | Canned/frozen processor, PA headquarters | Same (profile text) | 10-K FY2004 Item 1 |
| Share classes | Class A quoted; Class B family control | Same | 10-K; SC 13E3 |
| SEC reporting | Last regular 10-K FY2004 | Same | EDGAR submissions |
| Component proofs | Operating **$72.02/sh**; reserve **−$10.78/sh** | No approved external value | `evidence_reconciliation_2026-07-21.md` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Current book / debt | Proof uses **~$87.62/sh** [Assumption] | Aggregator same | Do not blend until human verifies source document |
| Implied return | Base **3.9%** partial re-rate | n/a | Marvin only |
| Appraisal-style BVPS | Falsifier ceiling only | Occasional **$300+** claims online | Exclude from base |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **~$61.24/sh** component base | **3.9%** / 7y | **watch** |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **3.9%** | **watch** |

**Weights:** 100% Marvin filing anchor plus explicit [Assumption] market inputs; 0% unapproved third party.

**Returns statement (blended):** At **~$55**, Marvin base **3.9%** per year pending verified financials; no external blend.

## [HUMAN REVIEW]

- [ ] Verify aggregator book and debt against a current shareholder report
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Promote any external source via `_system/frameworks/third_party_sources.md` before base IRR use

## Primary sources cited

1. `HNFSA/research/deep_dive_2026-07-21.md`
2. `HNFSA/research/valuation.json`
3. `HNFSA/research/evidence_reconciliation_2026-07-21.md`
4. `HNFSA/third-party-analyses/source_inventory_2026-07-20.md`
