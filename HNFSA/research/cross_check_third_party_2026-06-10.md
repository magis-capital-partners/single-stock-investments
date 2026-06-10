# HNFSA — Cross-Check: Third-Party Sources

**Date:** 2026-06-10
**Agent:** Marvin
**Marvin dive:** `HNFSA/research/deep_dive_2026-06-10.md`
**Source inventory:** `HNFSA/third-party-analyses/source_inventory_2026-06-10.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for HNFSA as of this scan. Marvin stance rests on **primary SEC filings** (FY2004 10-K, December 2004 SC 13E3) plus **[Assumption]** aggregator market data flagged in the deep dive. Aggregator statistics (book **~$87.62/sh**, revenue **~$331M**) are **context only** and are **not** approved third-party inputs for base IRR.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Used in base IRR? |
|--------|------|--------|-------------------|
| (none indexed) | — | — | n/a |
| Aggregator snapshots (Stockanalysis/Yahoo) | Web context | **[Assumption] / pending** | **No** |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Business | Canned/frozen processor, PA headquarters | Same (profile text) | 10-K FY2004 Item 1 |
| Share classes | Class A quoted; Class B family control | Same | 10-K; SC 13E3 |
| SEC reporting | Last regular 10-K FY2004 | Same | EDGAR submissions API |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Current book / debt | Not verified in filings | Aggregator book **~$87.62**, debt **~$62M** | Do not blend until human verifies source document |
| Implied return | Base **3.9%** partial re-rate | n/a | Marvin only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | Partial book re-rate **$72/sh** Y7 | **3.9%** / 7y | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **Marvin floor only** | **3.9%** | **watch** |

**Weights:** 100% Marvin filing anchor + explicit [Assumption] market inputs; 0% unapproved third party.

**Returns statement (blended):** At **~$55**, Marvin base **3.9%** per year pending verified financials; no external blend.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings (none indexed)
- [ ] Every **pending** source cited with **[Assumption]** only (aggregators)
- [ ] Promote verified shareholder PDF to inventory before blending into IRR

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] HNFSA third-party cross-check 2026-06-10: Marvin floor only; OTC disclosure gap.

## Primary sources cited

1. `HNFSA/research/deep_dive_2026-06-10.md`
2. `HNFSA/investor-documents/sec-edgar/10-K_20040830_rpt20040531_acc000095011604002631.htm`
3. `HNFSA/investor-documents/sec-edgar/SC13E3_20041206_acc000095011604003686.txt`
4. `HNFSA/third-party-analyses/source_inventory_2026-06-10.md`
