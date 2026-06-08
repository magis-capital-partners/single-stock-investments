# WPM — Cross-Check: Third-Party Sources

**Date:** 2026-06-08
**Agent:** Marvin
**Marvin dive:** `WPM/research/deep_dive_2026-06-08.md`
**Source inventory:** `WPM/third-party-analyses/source_inventory_2026-06-08.md`
**Framework:** `_system/frameworks/third_party_cross_reference.md`, `external_view_blend.md`

## Executive summary

Marvin floor from primary filings and `valuation.json` (Lawrence base on mid-cycle **$3.00 per share** owner cash). No third-party sources indexed; filings-only stance unchanged from 2026-06-07. **[HUMAN REVIEW]** for approved-source numeric blend.

**Synthesis (best estimate):** EX-99.1 FY2025 results remain the filing anchor. Antamina close was expected **April 1, 2026** per EX-99.1; no post-close filing in folder as of 2026-06-08. May 2026 dividend press release confirms **$0.195 per share** quarterly policy (+18% vs 2025) already disclosed in EX-99.1; no change to owner-cash normalization or stance.

## Sources in scope

| Source ID | Title | Path | Status | Cross-check status |
|-----------|-------|------|--------|-------------------|
| (none) | Primary filings only | — | — | n/a |

## Agreements (facts)

| Topic | Marvin (filings) | External | Source |
|-------|------------------|----------|--------|
| FY2025 operating cash flow per share | **$4.197** basic | n/a | EX-99.1 |
| 2026 GEO guidance | **860,000 to 940,000** | n/a | EX-99.1 |
| 2030 production outlook | **~1.2 million GEOs** | n/a | EX-99.1 |
| Antamina deal | **$4.3 billion** upfront; **67.5%** silver from Apr 2026 | n/a | EX-99.1 |
| 2026 quarterly dividend | **$0.195 per share** | Press release aligns | EX-99.1; `news_index.json` |
| Normalization | Mid-cycle **$3.00 per share** start | n/a | `valuation.json` |
| Stance | **watch** | n/a | `valuation.json` |

## Divergences (normalization / stance)

| Topic | Marvin floor | External | Blend logic |
|-------|--------------|----------|-------------|
| Primary IRR | Lawrence base (mid-cycle owner cash) | No approved IRR | Marvin **100%** numeric until human promotes external |
| 2026 volume uplift | Embedded in growth assumption, not starting cash flow | n/a | Filing supports growth narrative; not silent cash-flow bump |
| Antamina close (post-Apr 2026) | Expected Apr 1 2026 per EX-99.1 | No 8-K in folder (2026-06-08) | **[HUMAN REVIEW]** delivery vs guidance; download gap |

## Blended estimate (best judgment)

| Lens | Owner cash / value | Return / horizon | Stance hint |
|------|-------------------|------------------|-------------|
| Marvin floor | **$3.00 per share** mid-cycle | Lawrence base (refresh) | **watch** |
| External (combined) | — | No change to base % | **watch** (conviction) |
| **Blended best estimate** | **Filing anchor** | Lawrence base | **watch** |

**Weights:** Marvin **100%** on numbers (no approved external); qualitative layer unchanged.

**Returns statement (blended):** We expect the Marvin Lawrence base annual return at today's price on **$3.00 per share** starting owner cash; third-party sources may adjust conviction on timing but do not replace filing math without **[HUMAN REVIEW]**.

## [HUMAN REVIEW]

- [ ] Every **approved** source reviewed against filings
- [ ] Every **pending** source cited with **[PENDING APPROVAL]** only
- [ ] Blended estimate in `valuation.json` → `estimates.external[]` if material
- [ ] Confirm Antamina stream closed and silver deliveries on schedule (expected Apr 1 2026; no post-close filing in folder as of 2026-06-08)

## [PROPOSED MEMORY]

- [PROPOSED COMPANY] WPM: third-party cross-check 2026-06-08 — no indexed sources; EX-99.1 filing anchor; Antamina close filing gap; dividend press confirms EX-99.1 policy

## Primary sources cited

1. `WPM/investor-documents/sec-edgar/EX99_1_2025_results_202602.htm`
2. `WPM/research/deep_dive_2026-06-08.md`
3. `WPM/research/valuation.json`
4. `WPM/research/news/news_index.json`
