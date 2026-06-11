# BSM — Cross-Check: Third-Party Sources

**Date:** 2026-06-11
**Agent:** Marvin
**Marvin dive:** `BSM/research/deep_dive_2026-06-11.md`
**Source inventory:** `BSM/third-party-analyses/source_inventory_2026-06-11.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No third-party sources are indexed for this ticker as of this scan. Marvin stance rests on **primary filings only** (10-K, 10-Q, IR). Horizon Kinetics Q1 2026 13F shows **~151,238** units (~**$2.3M** value per screen); cited as **context only**, not approved for base IRR.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary filings | 10-K / 10-Q / DEF 14A | approved (primary) | Marvin floor |
| HK 13F (Q1 2026) | Context | pending | Holding size only; no HK commentary PDF indexed for BSM |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| Business model | Mineral/royalty MLP; passive toll | HK holds position (context) | 10-K; royalty_king_hk_screen |
| Scale | 20.3M net mineral/royalty acres | n/a | 10-K Acreage |
| Distributions | FY2025 ~$1.35/common unit | n/a | 10-K cash flow |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Undeveloped acreage value | Excluded from Lawrence base | Not modeled externally | No approved external NAV; overlay context only |
| Stance | watch at 9.4% base | n/a | Filings-only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $1.35/unit distributions | 9.4% / 7yr | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$1.35/unit** | **9.4%** | **watch** |

**Weights:** 100% Marvin filings (no approved third-party sources).

**Returns statement (blended):** At ~$13.88 per unit, Marvin's filing-based base case is **9.4%** per year; no external sources in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] BSM: inaugural deep dive 2026-06-11; FY2025 distributions ~$1.35/unit; 20.3M net mineral acres; Lawrence base 9.4%; stance watch.

## Primary sources cited

1. `BSM/research/deep_dive_2026-06-11.md`
2. `BSM/third-party-analyses/source_inventory_2026-06-11.md`
