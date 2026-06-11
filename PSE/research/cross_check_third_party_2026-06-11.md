# PSE — Cross-Check: Third-Party Sources

**Date:** 2026-06-11
**Agent:** Marvin
**Marvin dive:** `PSE/research/deep_dive_2026-06-11.md`
**Source inventory:** `PSE/third-party-analyses/source_inventory_2026-06-11.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`
<!-- THIRD_PARTY_CROSS_CHECK_STUB -->

## Executive summary

No approved third-party sources are indexed for PSE as of 2026-06-11. Marvin stance rests on **primary SEC Philippines filings** (Form 17-A, 17-Q, audited financial statements) and PSE edge market data for spot price. Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend. Base synthesis IRR **14.09%** per year at PHP 211.00.

## Sources in scope

| Source | Type | Status | Role |
|--------|------|--------|------|
| Primary filings | SEC Form 17-A/Q | on disk | Revenue, PDSHC consolidation, owner cash |
| PSE edge market data | exchange | context | PHP 211.00, 82.27M shares |
| Third-party inventory | scan | empty | No approved external views |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 gross revenue | PHP 2.84B | n/a | `annual_report_2025.pdf` |
| FY2025 EPS (basic) | PHP 14.11 | n/a | `audited_financials_dec_2025.pdf` |
| PDSHC consolidation | Majority stake 2024–2025 | n/a | `quarterly_report_3q_2025.pdf` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | PHP 14.00/sh owner cash | 14.09% / 7yr synthesis | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **PHP 14.00/sh** | **14.09% / 7yr** | **watch** |

**Weights:** 100% Marvin filings (no approved external sources).

**Returns statement (blended):** At PHP 211.00 per share we expect about **14.09% per year** over seven years on PHP 14.00 normalized owner cash per share, filings only.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] PSE: third-party cross-check 2026-06-11

## Primary sources cited

1. `PSE/research/deep_dive_2026-06-11.md`
2. `PSE/third-party-analyses/source_inventory_2026-06-11.md`
