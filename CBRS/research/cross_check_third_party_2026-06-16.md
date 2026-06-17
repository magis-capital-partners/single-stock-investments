# CBRS — Cross-Check: Third-Party Sources

**Date:** 2026-06-16
**Agent:** Marvin
**Marvin dive:** `CBRS/research/deep_dive_2026-06-16.md`
**Source inventory:** `CBRS/third-party-analyses/source_inventory_2026-06-16.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

No approved or pending third-party research PDFs are indexed for Cerebras as of 2026-06-16. Public IPO commentary (Motley Fool, IPOScoop, Bloomberg oversubscription reports) is **context tier only** and is not blended into Lawrence base IRR. Marvin stance rests on the **S-1 registration statement** (April 17, 2026), **IPO closing 8-K** (May 15, 2026), and company press release on the offering close.

**Synthesis:** Marvin floor only; no external blend.

## Sources in scope

| Source | Type | Status | In base IRR? |
|--------|------|--------|--------------|
| `CBRS/investor-documents/sec-edgar/S-1_20260417_rpt20260417_acc0001628280_26_025762.htm` | Primary SEC | filing | yes (floor) |
| `CBRS/investor-documents/sec-edgar/8-K_20260515_rpt20260515_acc0001628280_26_035605.htm` | Primary SEC | filing | yes (floor) |
| Motley Fool / IPOScoop IPO articles | Web context | pending | no |
| HK vault | n/a | n/a | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| IPO price | $185.00 per share, 34.5M Class A sold | Same | 8-K Item 8.01 |
| FY2025 revenue | $510.0M (+76% YoY) | Same in IPO commentary | S-1 summary |
| FY2025 net income | $237.8M (includes one-time gain) | Same | S-1 consolidated statements |
| OpenAI deal | Multi-year MRA, $20B+ value, 750 MW | Same | S-1 business/risk sections |
| Customer concentration | MBZUAI 62%, G42 24% of FY2025 revenue | Not always highlighted | S-1 risk factors |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Earnings quality | Strip $363.3M forward-contract gain; operating loss $145.9M | IPO articles cite GAAP net income as "profitable" | Marvin uses normalized owner cash, not headline net income |
| Valuation | Scenario IRR on normalized $0.18/sh owner cash | IPO buzz focuses on first-day pop from $185 to ~$311 | No external IRR anchor approved |
| Moat | Unproven vs NVIDIA CUDA ecosystem | Bullish AI chip narrative | Context only |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | $0.18/sh normalized starting owner cash | Scenario base (computed in valuation.json) | watch |
| External (combined) | n/a | n/a | n/a |
| **Blended best estimate** | **Marvin floor only** | **Pending mechanical refresh** | **watch** |

**Weights:** 100% Marvin floor. No approved external sources.

**Returns statement (blended):** Same as Lawrence base case after `marvin_cloud_refresh.py`; pending sources not in base IRR.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material third party added later
- [ ] Verify live CBRS price vs placeholder in valuation.json after refresh

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] CBRS: first deep dive 2026-06-16; IPO May 2026; Lawrence base uses normalized owner cash not GAAP net income inflated by forward-contract gain.

## Primary sources cited

1. `CBRS/research/deep_dive_2026-06-16.md`
2. `CBRS/investor-documents/sec-edgar/S-1_20260417_rpt20260417_acc0001628280_26_025762.htm`
3. `CBRS/investor-documents/sec-edgar/8-K_20260515_rpt20260515_acc0001628280_26_035605.htm`
4. `CBRS/third-party-analyses/source_inventory_2026-06-16.md`
