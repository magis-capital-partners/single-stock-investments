# AAPL — Cross-Check: Third-Party Sources

**Date:** 2026-07-21  
**Agent:** Marvin (contract backfill)  
**Marvin dive:** `AAPL/research/deep_dive_2026-07-21.md`  
**Source inventory:** `AAPL/third-party-analyses/source_inventory_2026-07-21.md`  
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved third-party sources are indexed for AAPL as of this scan. Institutional SC 13G filings (Berkshire historical stake, other holders) are **context tier** only per `third_party_sources.md`. Marvin stance rests on **primary filings** (10-K, 10-Q, IR). Re-run `scan_third_party_sources.py` when Substacks or HK material is added.

**Synthesis:** Marvin floor only; no external blend in base IRR.

## Sources in scope

| Source | Tier | Path | Role |
|--------|------|------|------|
| SC 13G/A filings (historical) | context | `AAPL/third-party-analyses/activist_reports/long/` | Historical ownership; not in base IRR |
| Source inventory scan | mechanical | `AAPL/third-party-analyses/source_inventory_2026-07-21.md` | Confirms zero approved third-party analyses |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue scale | **$307.0B** consolidated net sales | No approved external | `10-K_20251031_rpt20250927` |
| Services mix | **$109.2B** disaggregated Services net sales | No approved external | Same 10-K disaggregated table |
| Free cash generation | **$98.8B** FCF (OCF **$111.5B** less capex **$12.7B**) | No approved external | Same 10-K cash-flow statement |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| — | — | — | No external views to blend |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor (component sum base) | **$187/sh** | Mechanical Lawrence path in Phase 3 | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$187/sh** (components) | **Pending mechanical refresh** | **watch** |

**Weights:** 100% Marvin filing-locked components; 0% external (none approved).

**Returns statement (blended):** Base case follows Marvin component schedule and Lawrence path only; no third-party inputs in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings when inventory adds entries
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] AAPL: third-party cross-check 2026-07-21 confirms primary-filings-only base; component schedule **$187/sh** vs **~$327** price.

## Primary sources cited

1. `AAPL/investor-documents/sec-edgar/10-K_20251031_rpt20250927_acc0000320193_25_000079.htm`
2. `AAPL/investor-documents/sec-edgar/10-Q_20260501_rpt20260328_acc0000320193_26_000013.htm`
3. `AAPL/research/evidence_reconciliation_2026-07-21.md`
4. `AAPL/third-party-analyses/source_inventory_2026-07-21.md`
