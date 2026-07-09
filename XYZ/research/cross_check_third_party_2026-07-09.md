# XYZ — Cross-Check: Third-Party Sources

**Date:** 2026-07-09
**Agent:** Marvin
**Marvin dive:** `XYZ/research/deep_dive_2026-07-09.md`
**Source inventory:** `XYZ/third-party-analyses/source_inventory_2026-07-09.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No third-party sources are indexed for Block (XYZ) as of this scan. Marvin stance rests on **primary filings only** (FY2025 10-K, Q1 2026 10-Q, proxy). Re-run `scan_third_party_sources.py` when Substacks, fund letters, or HK material is added.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 revenue | $11.5B (+10% YoY) | — | `10-K_20260226` |
| FY2025 gross profit | $10.4B | — | `10-K_20260226` |
| Q1 2026 gross profit growth | +27% YoY | — | `10-Q_20260507` |
| Cash App ex-bitcoin growth | +37% net revenue Q1-26 | — | `10-Q_20260507` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Owner cash per share | $3.89 (OCF − capex FY25) | — | No external normalization to blend |
| Stance | watch (<15% base IRR at ~$77) | — | Filings-only gate |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $3.89/sh owner cash | Base case computed in `valuation.json` | watch |
| External (combined) | — | — | — |
| **Blended best estimate** | **$3.89/sh** | **Filings-only Lawrence base** | **watch** |

**Weights:** 100% Marvin floor (no approved external sources).

**Returns statement (blended):** Pending `marvin_valuation.py --write`; filings-only base IRR drives stance.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] XYZ (Block): platform with Cash App + Square segments; FY2025 owner cash ~$3.89/sh; bitcoin ecosystem is low-margin (2-4% of GP); stance watch at ~$77 pending third-party sources.

## Primary sources cited

1. `XYZ/investor-documents/sec-edgar/10-K_20260226_rpt20251231_acc0001628280_26_012254.htm`
2. `XYZ/investor-documents/sec-edgar/10-Q_20260507_rpt20260331_acc0001628280_26_032200.htm`
3. `XYZ/research/deep_dive_2026-07-09.md`
4. `XYZ/third-party-analyses/source_inventory_2026-07-09.md`
